#!/usr/bin/env python3
"""Read-only scheduled input resolver. No service calls occur on import.

CLI is a local proposal, not activated. Transport is injected in offline tests.
Only fixed GitHub API GETs and fixed public live-site GETs are issued; token is
never logged, written, included in outputs, or forwarded to download/live hosts.
"""
import argparse
import base64
import datetime as dt
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'MametaroGG/booth-vrc-price-tracker'
API = 'https://api.github.com'
PREFIX = '/repos/' + REPOSITORY
WORKFLOW = '.github/workflows/daily_scrape.yml'
LIVE = 'https://mametarogg.github.io/boopadb'
MAX_BYTES = 8 * 1024 * 1024
MAX_AGE = dt.timedelta(hours=24)
SHA40 = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
DIGITS = re.compile(r'[1-9][0-9]*\Z')
SOURCE_FILES = ('src/scraper.js', 'src/collection-receipt.js', 'src/collection-runtime.js',
                'src/continuation.js', 'scripts/push-data.sh', 'write-save-receipt.cjs')

class Refused(ValueError):
    pass

def need(condition, message):
    if not condition:
        raise Refused(message)

def digest(b):
    return hashlib.sha256(b).hexdigest()

def parse(b):
    # Duplicate keys are ambiguous evidence, not last-key-wins configuration.
    def pairs(values):
        out = {}
        for k, v in values:
            need(k not in out, 'Duplicate JSON key')
            out[k] = v
        return out
    return json.loads(b, object_pairs_hook=pairs)

def timestamp(value):
    need(isinstance(value, str), 'Missing timestamp')
    try:
        out = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as e:
        raise Refused('Malformed timestamp') from e
    need(out.tzinfo is not None, 'Timestamp must include timezone')
    return out

def positive(v):
    return type(v) is int and v > 0

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Transport:
    """GET only, bounded responses, redirects handled explicitly by caller."""
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, url, headers):
        try:
            req = urllib.request.Request(url, headers=headers, method='GET')
            response = self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            response = e
        except (urllib.error.URLError, TimeoutError, ValueError, OSError, http.client.HTTPException):
            # Never include URL containing signed download query or credentials.
            raise Refused('Read transport failed; no selection emitted') from None
        with response:
            body = response.read(MAX_BYTES + 1)
            need(len(body) <= MAX_BYTES, 'Response exceeds size limit')
            return response.status, dict(response.headers.items()), body

class Resolver:
    def __init__(self, token, request=None, now=None):
        need(isinstance(token, str) and token and not any(c.isspace() for c in token),
             'Existing read-only GITHUB_TOKEN is required')
        self._token = token
        self.request = request or Transport()
        self.now = now or dt.datetime.now(dt.timezone.utc)

    def api(self, endpoint):
        need(endpoint.startswith(PREFIX + '/') or endpoint == PREFIX, 'API repository is fixed')
        status, headers, body = self.request(API + endpoint, {
            'Authorization': 'Bearer ' + self._token,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'boopadb-input-resolver'})
        need(status == 200, f'GitHub read returned HTTP {status}; required contents/actions read access unavailable or state missing')
        return parse(body)

    def contents(self, filename, commit):
        need(SHA40.fullmatch(commit or '') is not None, 'Immutable commit required')
        item = self.api(PREFIX + '/contents/' + urllib.parse.quote(filename, safe='/') + '?ref=' + commit)
        need(item.get('type') == 'file' and item.get('path') == filename and item.get('encoding') == 'base64',
             'Unexpected contents response')
        try:
            b = base64.b64decode(''.join(item['content'].split()), validate=True)
        except (ValueError, KeyError):
            raise Refused('Malformed file bytes') from None
        need(len(b) <= MAX_BYTES and item.get('size') == len(b), 'Contents size mismatch')
        git_blob = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
        need(item.get('sha') == git_blob, 'Contents Git blob mismatch')
        return b

    def archive(self, artifact):
        artifact_id = artifact.get('id')
        need(positive(artifact_id), 'Invalid artifact ID')
        endpoint = PREFIX + f'/actions/artifacts/{artifact_id}/zip'
        status, headers, body = self.request(API + endpoint, {
            'Authorization': 'Bearer ' + self._token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'boopadb-input-resolver'})
        if status == 302:
            location = next((v for k, v in headers.items() if k.lower() == 'location'), '')
            u = urllib.parse.urlsplit(location)
            need(u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443) and
                 u.hostname and (u.hostname.endswith('.blob.core.windows.net') or
                                 u.hostname.endswith('.actions.githubusercontent.com')),
                 'Unexpected artifact redirect host')
            # NO Authorization on a signed artifact URL; reject further redirects.
            status, _, body = self.request(location, {'User-Agent': 'boopadb-input-resolver'})
        need(status == 200, f'Artifact download returned HTTP {status}')
        need(len(body) <= MAX_BYTES, 'Artifact archive too large')
        expected = artifact.get('digest', '')
        need(isinstance(expected, str) and expected == 'sha256:' + digest(body), 'Missing/mismatched artifact digest')
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            entries = z.infolist()
            need(len(entries) == 1 and entries[0].filename == 'saved-collection.json' and
                 entries[0].file_size <= 65536 and not entries[0].is_dir() and
                 (entries[0].external_attr >> 16) & 0o170000 != 0o120000,
                 'Unexpected artifact archive entries')
            receipt = parse(z.read(entries[0]))
        return receipt

    def live_bytes(self, filename, absent_ok=False):
        status, _, b = self.request(LIVE + '/' + filename, {'Cache-Control': 'no-cache',
                'User-Agent': 'boopadb-input-resolver'})
        if status == 404 and absent_ok:
            return None
        need(status == 200, f'Live {filename} read returned HTTP {status}; absence cannot be inferred')
        need(len(b) <= MAX_BYTES, 'Live file too large')
        return b

    def select_run(self):
        repo = self.api(PREFIX)
        need(repo.get('full_name') == REPOSITORY and positive(repo.get('id')) and
             isinstance(repo.get('default_branch'), str) and repo['default_branch'], 'Repository identity mismatch')
        workflow = self.api(PREFIX + '/actions/workflows/daily_scrape.yml')
        need(workflow.get('path') == WORKFLOW and workflow.get('state') == 'active' and positive(workflow.get('id')),
             'Collector workflow identity/state mismatch')
        branch = urllib.parse.quote(repo['default_branch'], safe='')
        listing = self.api(PREFIX + f'/actions/workflows/{workflow["id"]}/runs?branch={branch}&status=completed&per_page=100&page=1')
        runs = listing.get('workflow_runs')
        need(isinstance(runs, list) and runs, 'No terminal collector run')
        need(all(positive(r.get('run_number')) and positive(r.get('id')) for r in runs), 'Malformed run list')
        # Deterministic polling rule: newest collector run number among terminal
        # runs, not latest main, event SHA, latest successful run, or arbitrary rerun.
        number = max(r['run_number'] for r in runs)
        candidates = [r for r in runs if r['run_number'] == number]
        need(len(candidates) == 1, 'Ambiguous newest terminal collector run')
        run = self.api(PREFIX + f'/actions/runs/{candidates[0]["id"]}')
        self.check_run(run, repo, workflow)
        need(run['run_number'] == number, 'Run changed during selection')
        return repo, workflow, run

    def check_run(self, run, repo, workflow):
        need(run.get('repository', {}).get('id') == repo['id'] and
             run.get('repository', {}).get('full_name') == REPOSITORY and
             run.get('head_repository', {}).get('id') == repo['id'] and
             run.get('workflow_id') == workflow['id'] and run.get('path') == WORKFLOW and
             run.get('head_branch') == repo['default_branch'] and
             run.get('event') in ('schedule', 'workflow_dispatch', 'repository_dispatch') and
             run.get('status') == 'completed' and run.get('conclusion') == 'success' and
             positive(run.get('run_attempt')) and SHA40.fullmatch(run.get('head_sha', '')) is not None,
             'Newest terminal run is not trusted collector success; no older-run fallback')
        when = timestamp(run.get('updated_at'))
        need(dt.timedelta(0) <= self.now - when <= MAX_AGE, 'Collector run is stale or future-dated')

    def resolve(self, workdir, baseline_pin, baseline_sha, producer_pin):
        workdir = Path(workdir)
        need(not workdir.exists(), 'Resolver work directory must be new')
        workdir.mkdir(parents=True)
        pin = parse(Path(producer_pin).read_bytes())
        need(pin.get('schema') == 'boopa-producer-pin-v1' and pin.get('repository') == REPOSITORY and
             set(pin.get('files_sha256', {})) == set(SOURCE_FILES) and
             isinstance(pin.get('source_root_entries'), dict) and bool(pin['source_root_entries']), 'Malformed reviewed producer pin')
        for value in [pin.get('workflow_sha256')] + list(pin['files_sha256'].values()):
            need(isinstance(value, str) and SHA256.fullmatch(value) is not None, 'Invalid producer file pin')
        baseline_bytes = Path(baseline_pin).read_bytes()
        need(digest(baseline_bytes) == baseline_sha, 'Baseline pin bytes changed')
        repo, workflow, run = self.select_run()
        run_id, attempt = run['id'], run['run_attempt']
        jobs = self.api(PREFIX + f'/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=1')
        need(jobs.get('total_count') == 1 and len(jobs.get('jobs', [])) == 1, 'Ambiguous collector job')
        job = jobs['jobs'][0]
        need(job.get('run_id') == run_id and job.get('run_attempt') == attempt and job.get('name') == 'scrape' and
             job.get('status') == 'completed' and job.get('conclusion') == 'success', 'Collector job mismatch')
        for name, expected in [('Verify reviewed source before dependencies', 'success'),
                               ('Verify reviewed source before collection', 'success'),
                               ('Verify reviewed source after save', 'success'), ('Run Scraper', 'success'), ('Commit and Push', 'success'),
                               ('Report scraper failure', 'skipped'),
                               ('Record immutable saved collection', 'success'),
                               ('Retain immutable saved collection', 'success')]:
            steps = [s for s in job.get('steps', []) if s.get('name') == name]
            need(len(steps) == 1 and steps[0].get('conclusion') == expected, 'Missing/ambiguous collector step: ' + name)
        artifacts = self.api(PREFIX + f'/actions/runs/{run_id}/artifacts?per_page=100&page=1')
        need(type(artifacts.get('total_count')) is int and artifacts['total_count'] <= 100 and
             artifacts['total_count'] == len(artifacts.get('artifacts', [])), 'Artifact listing incomplete')
        name = f'boopadb-collector-{run_id}-{attempt}'
        matches = [a for a in artifacts['artifacts'] if a.get('name') == name]
        need(len(matches) == 1, 'Missing/ambiguous run-attempt artifact')
        artifact = matches[0]
        need(artifact.get('expired') is False and artifact.get('workflow_run', {}).get('id') == run_id and
             artifact.get('workflow_run', {}).get('head_sha') == run['head_sha'] and
             artifact.get('workflow_run', {}).get('head_branch') == repo['default_branch'], 'Artifact run binding mismatch')
        need(timestamp(artifact.get('expires_at')) > self.now, 'Artifact expired')
        saved = self.archive(artifact)
        need(saved.get('repository') == REPOSITORY and saved.get('run_id') == str(run_id) and
             saved.get('run_attempt') == str(attempt) and saved.get('scraper_outcome') == 'success' and
             saved.get('save_outcome') == 'success' and SHA40.fullmatch(saved.get('tracker_commit', '')) is not None,
             'Saved-collection attempt/original-outcome mismatch')
        # Pin workflow that GitHub evaluated, separately from checkout code source.
        need(digest(self.contents(WORKFLOW, run['head_sha'])) == pin['workflow_sha256'], 'Unreviewed workflow definition')
        commit = saved['tracker_commit']
        commit_object = self.api(PREFIX + '/git/commits/' + commit)
        need(commit_object.get('sha') == commit, 'Saved object is not authenticated Git commit')
        materialized = workdir / 'tracker-proof'
        (materialized / 'data').mkdir(parents=True)
        for filename in ('data/collection_receipt.json', 'data/request_budget.json', 'data/crawl_state.json'):
            (materialized / filename).write_bytes(self.contents(filename, commit))
        receipt = parse((materialized / 'data/collection_receipt.json').read_bytes())
        source_commit = receipt.get('source_commit')
        need(isinstance(source_commit, str) and SHA40.fullmatch(source_commit) is not None, 'Missing actual collector checkout source commit')
        # Verify actual pre-scrape and post-save source roots independently of the
        # receipt's claim. The pinned workflow also gates these exact trees and
        # clean worktree before dependencies, after reservation rebase, and after
        # final-save rebase BEFORE continuation/artifact code can execute.
        for source in set((source_commit, commit)):
            tree = self.api(PREFIX + '/git/trees/' + source)
            need(tree.get('truncated') is False and isinstance(tree.get('tree'), list), 'Incomplete source tree')
            entries = tree['tree']
            need(len({e['path'] for e in entries}) == len(entries), 'Duplicate tree path')
            actual = {e['path']: {k:e[k] for k in ('mode','type','sha')} for e in entries
                      if e['path'] not in ('data','meta','.github')}
            need(actual == pin['source_root_entries'], 'Unreviewed actual collector source tree')
        for filename in SOURCE_FILES:
            need(digest(self.contents(filename, source_commit)) == pin['files_sha256'][filename], 'Unreviewed collector source: ' + filename)
        stopped = receipt.get('stopped_at_ms')
        need(type(stopped) is int and 0 <= self.now.timestamp() * 1000 - stopped <= MAX_AGE.total_seconds() * 1000,
             'Collector receipt observation time stale or future')
        ledger = parse((materialized / 'data/request_budget.json').read_bytes())
        source_date = ledger.get('date')
        try:
            observation_day = dt.date.fromisoformat(source_date)
        except (TypeError, ValueError):
            raise Refused('Invalid source date') from None
        today = (self.now + dt.timedelta(hours=9)).date()
        need(0 <= (today - observation_day).days <= 1, 'Saved observation date stale or future')
        live_dir = workdir / 'live'
        live_dir.mkdir()
        first_release = self.live_bytes('release-manifest.json', absent_ok=True)
        if first_release is not None:
            (live_dir / 'release-manifest.json').write_bytes(first_release)
        else:
            for filename in ('index.html', 'item.html', 'snapshot-manifest.json'):
                (live_dir / filename).write_bytes(self.live_bytes(filename))
        # A second live-manifest read brackets baseline materialization and detects
        # concurrent promotion. Promotion still rechecks lineage immediately before use.
        need(self.live_bytes('release-manifest.json', absent_ok=True) == first_release, 'Live lineage changed during resolver read')
        trusted = dict(repository=REPOSITORY, workflow_path=WORKFLOW,
                       default_branch=repo['default_branch'], head_branch=run['head_branch'],
                       run_id=str(run_id), run_attempt=str(attempt), status=run['status'], conclusion=run['conclusion'],
                       scraper_outcome=saved['scraper_outcome'], save_outcome=saved['save_outcome'])
        config = dict(materializedDir=str(materialized.resolve()), saveReceipt=saved, trustedRun=trusted,
                      liveDir=str(live_dir.resolve()), baselinePinPath=str(Path(baseline_pin).resolve()),
                      expectedBaselinePinSha256=baseline_sha, expectedDate=source_date)
        config_path = workdir / 'selector-config.json'
        config_path.write_text(json.dumps(config))
        script = Path(__file__).with_name('select-input.cjs').resolve()
        command = "const fs=require('node:fs'),m=require(process.argv[1]),c=JSON.parse(fs.readFileSync(process.argv[2]));c.baselinePinBytes=fs.readFileSync(c.baselinePinPath);console.log(JSON.stringify(m.selectMaterialized(c)));"
        result = subprocess.run(['node', '-e', command, str(script), str(config_path.resolve())],
                                capture_output=True, text=True, check=False)
        need(result.returncode == 0, 'Saved collector/live lineage consistency check failed: ' + result.stderr.strip()[:500])
        selection = parse(result.stdout)
        # Re-read selected attempt after all downloads: a rerun or changed terminal
        # state invalidates this proof, never silently substitutes another attempt.
        final_repo, final_workflow, final_run = self.select_run()
        need(final_repo == repo and final_workflow == workflow and final_run['id'] == run_id and
             final_run['run_attempt'] == attempt and final_run['head_sha'] == run['head_sha'],
             'Newest terminal collector run/attempt changed during resolution')
        selection['selection_authority'] = 'authenticated-github-read-and-live-lineage'
        proof = dict(schema='boopa-resolved-inputs-v1', repository=REPOSITORY, run_id=str(run_id),
                     run_attempt=str(attempt), artifact_id=artifact['id'], artifact_digest=artifact['digest'],
                     source_commit=source_commit, producer_pin_sha256=digest(Path(producer_pin).read_bytes()),
                     evaluated_at=self.now.isoformat(), selection=selection)
        (workdir / 'resolved-inputs.json').write_text(json.dumps(proof, indent=2) + '\n')
        return proof

def finalize_context(selection_path, inventory_path, output, env=None):
    env = os.environ if env is None else env
    proof = parse(Path(selection_path).read_bytes())
    s = proof.get('selection', {})
    need(proof.get('schema') == 'boopa-resolved-inputs-v1' and
         s.get('selection_authority') == 'authenticated-github-read-and-live-lineage', 'Missing authenticated resolver output')
    need(env.get('GITHUB_ACTIONS') == 'true' and SHA40.fullmatch(env.get('GITHUB_SHA', '')) is not None and
         DIGITS.fullmatch(env.get('GITHUB_RUN_ID', '')) is not None and
         DIGITS.fullmatch(env.get('GITHUB_RUN_ATTEMPT', '')) is not None, 'Generator workflow identity required')
    # Must be run in the same job immediately after trusted resolver+inventory;
    # no user-supplied arbitrary file is authentication by itself.
    context = dict(synthetic=False, tracker_commit=s['tracker_commit'], generator_commit=env['GITHUB_SHA'],
                   run_id=env['GITHUB_RUN_ID'], run_attempt=env['GITHUB_RUN_ATTEMPT'], generation=s['generation'],
                   prev_release_digest=s['prev_release_digest'], expected_date=s['expected_date'],
                   inventory_digest=digest(Path(inventory_path).read_bytes()))
    Path(output).write_text(json.dumps(context, indent=2) + '\n')
    return context

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='mode', required=True)
    r = sub.add_parser('resolve')
    for arg in ('workdir', 'baseline-pin', 'baseline-pin-sha256', 'producer-pin'):
        r.add_argument('--' + arg, required=True)
    f = sub.add_parser('finalize-context')
    for arg in ('selection', 'inventory', 'output'):
        f.add_argument('--' + arg, required=True)
    args = p.parse_args()
    try:
        if args.mode == 'resolve':
            proof = Resolver(os.environ.get('GITHUB_TOKEN')).resolve(args.workdir, args.baseline_pin,
                        args.baseline_pin_sha256, args.producer_pin)
            print(json.dumps(proof['selection']))
        else:
            finalize_context(args.selection, args.inventory, args.output)
    except Exception as e:
        # Do not print raw urllib requests/headers or signed URL errors.
        print('Automatic input resolution refused: ' + str(e)[:500], file=__import__('sys').stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
