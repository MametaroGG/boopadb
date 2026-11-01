import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.script=(ROOT/'source-gate.INLINE.py').read_text()
        self.entries=json.loads((ROOT/'producer-pin.PROPOSAL.json').read_text())['source_root_entries']
        self.others=b'';self.dirty=False;self.npmrc=False
    def gate(self):
        def output(args):
            if args==['git','ls-tree','-z','HEAD']:
                return b''.join(f"{v['mode']} {v['type']} {v['sha']}\t{k}".encode()+b'\0' for k,v in self.entries.items())
            if args==['git','ls-files','--others','-z']:return self.others
            raise AssertionError(args)
        def run(args,check):
            assert args==['git','diff','--exit-code','--quiet','HEAD','--','.',':!data',':!meta',':!.github']
            if self.dirty:raise subprocess.CalledProcessError(1,args)
        with patch('subprocess.check_output',side_effect=output),patch('subprocess.run',side_effect=run),patch('pathlib.Path.exists',return_value=self.npmrc):
            exec(compile(self.script,'trusted-workflow-inline','exec'),{})
    def test_exact_reviewed_source_passes(self):self.gate()
    def test_changed_source_before_scrape_or_after_rebase_rejected(self):
        self.entries['src']['sha']='0'*40
        with self.assertRaises(SystemExit):self.gate()
    def test_package_lock_tamper_rejected(self):
        self.entries['package-lock.json']['sha']='0'*40
        with self.assertRaises(SystemExit):self.gate()
    def test_extra_tracked_executable_rejected(self):
        self.entries['injected.js']=dict(mode='100644',type='blob',sha='f'*40)
        with self.assertRaises(SystemExit):self.gate()
    def test_dirty_worktree_rejected(self):
        self.dirty=True
        with self.assertRaises(subprocess.CalledProcessError):self.gate()
    def test_untracked_injected_require_rejected(self):
        self.others=b'src/injected.js\0'
        with self.assertRaises(SystemExit):self.gate()
    def test_untracked_npmrc_rejected(self):
        self.others=b'.npmrc\0'
        with self.assertRaises(SystemExit):self.gate()
    def test_existing_npmrc_rejected_even_if_git_ignored(self):
        self.npmrc=True
        with self.assertRaises(SystemExit):self.gate()
    def test_changing_data_metadata_and_installed_modules_allowed(self):
        self.entries['data']=dict(mode='040000',type='tree',sha='1'*40)
        self.entries['meta']=dict(mode='040000',type='tree',sha='2'*40)
        self.others=b'data/new.json\0meta/new.json\0node_modules/axios/index.js\0';self.gate()
    def test_gate_order_in_full_workflow(self):
        w=(ROOT/'proposed/.github/workflows/daily_scrape.yml').read_text()
        def at(n):return w.index('- name: '+n+'\n')
        self.assertLess(at('Verify reviewed source before dependencies'),at('Install dependencies'))
        self.assertLess(at('Commit reservation'),at('Verify reviewed source before collection'))
        self.assertLess(at('Verify reviewed source before collection'),at('Run Scraper'))
        self.assertLess(at('Commit and Push'),at('Verify reviewed source after save'))
        self.assertLess(at('Verify reviewed source after save'),at('Continue collection'))
        self.assertLess(at('Verify reviewed source after save'),at('Record immutable saved collection'))
        self.assertEqual(w.count('COLLECTOR_SOURCE_COMMIT=$(git rev-parse HEAD)'),1)

if __name__=='__main__':unittest.main()
