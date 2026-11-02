#!/usr/bin/env python3
"""Fail-closed one-use trial trigger/selection alignment, never authority minting.

Only run after a separately authorized workflow installation/activation. This
helper does not authenticate an owner grant or arbitrary proof JSON: selection
must be produced immediately before this check by the trusted GET-only resolver.
No network, grant, receipt, policy, deployment or collection operation is made.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = 'MametaroGG/boopadb'
TRACKER = 'MametaroGG/booth-vrc-price-tracker'
BRANCH = 'chore/auto-update-trial-20261101'
MARKER = '.github/boopadb-once/auto-update-20261102.json'
WORKFLOW = '.github/workflows/boopadb-nonpublic-once-20261102.yml'
MARKER_KEYS = {'schema', 'prepared_commit', 'collector_run_id',
               'collector_run_attempt', 'collector_saved_commit'}
SHA = re.compile(r'^[0-9a-f]{40}$')
NUMBER = re.compile(r'^[1-9][0-9]*$')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)


def sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def number(value):
    return isinstance(value, str) and NUMBER.fullmatch(value) is not None


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
        env={**os.environ, 'GIT_NO_REPLACE_OBJECTS': '1',
             'GIT_CONFIG_NOSYSTEM': '1'}, stderr=subprocess.DEVNULL)


def marker_path(root, marker):
    path = Path(marker)
    if not path.is_absolute():
        path = root / path
    require(path.resolve() == root / MARKER, 'Only the fixed activation marker is allowed')
    cursor = path.absolute()
    while cursor != cursor.parent:
        require(not cursor.is_symlink(), 'Activation marker path contains a symlink')
        cursor = cursor.parent
    require(path.is_file(), 'Actual activation marker is missing')
    return path


def marker_object(path):
    value = load(path)
    require(isinstance(value, dict) and set(value) == MARKER_KEYS and
            value['schema'] == 'boopa-once-v1', 'Exact one-use marker schema required')
    for key in ('prepared_commit', 'collector_saved_commit'):
        require(sha(value[key]), 'Malformed marker ' + key)
    for key in ('collector_run_id', 'collector_run_attempt'):
        require(number(value[key]), 'Malformed marker ' + key)
    return value


def validate_trigger(marker=MARKER, repo_root='.', env=None):
    env = os.environ if env is None else env
    root = Path(repo_root).resolve()
    require(env.get('GITHUB_ACTIONS') == 'true', 'Actual Actions identity required')
    require(env.get('GITHUB_REPOSITORY') == REPOSITORY, 'Wrong repository')
    require(env.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'Wrong trial branch')
    require(env.get('GITHUB_EVENT_NAME') == 'push', 'Only the explicitly authorized push trigger is allowed')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1', 'Reruns are not authorized')
    require(env.get('GITHUB_RUN_NUMBER') == '1', 'Only the first run of this dedicated workflow is authorized')
    require(number(env.get('GITHUB_RUN_ID')), 'Actual run ID required')
    after = env.get('GITHUB_SHA')
    require(sha(after), 'Immutable actual generator SHA required')
    # Anchors the workflow path as well as branch; no differently named workflow
    # can use this marker to acquire a new run-number namespace.
    require(env.get('GITHUB_WORKFLOW_REF') == REPOSITORY + '/' + WORKFLOW + '@refs/heads/' + BRANCH,
            'Wrong dedicated workflow identity')
    event_path = env.get('GITHUB_EVENT_PATH')
    require(isinstance(event_path, str) and event_path, 'Actual push event required')
    event = load(event_path)
    require(isinstance(event, dict) and event.get('repository', {}).get('full_name') == REPOSITORY,
            'Push event repository mismatch')
    require(event.get('ref') == env['GITHUB_REF'] and event.get('after') == after,
            'Push event branch/HEAD mismatch')
    require(event.get('deleted') is False and event.get('forced') is False,
            'Deletion/forced activation is not allowed')
    before = event.get('before')
    require(sha(before) and before != '0' * 40, 'Existing prepared commit required')
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == after,
            'Checkout differs from actual Actions SHA')
    parents = git(root, 'rev-list', '--parents', '-n', '1', after).decode().split()
    require(parents == [after, before], 'Activation must be a single non-merge commit on the prepared commit')
    # Shallow checkout with depth2 contains this direct parent. Do not fetch or
    # infer a missing object; fail closed instead.
    changed = git(root, 'diff-tree', '--no-commit-id', '--name-status', '-r', '-z', before, after).split(b'\0')
    require(changed == [b'A', MARKER.encode(), b''],
            'Activation commit must add only the dedicated marker; prepare code/config earlier')
    require(not git(root, 'ls-tree', before, '--', MARKER),
            'Marker already existed at preparation commit')
    path = marker_path(root, marker)
    require(path.read_bytes() == git(root, 'show', after + ':' + MARKER),
            'Marker worktree bytes differ from actual committed marker')
    value = marker_object(path)
    require(value['prepared_commit'] == before, 'Marker/prepared commit mismatch')
    return {'status': 'validated-one-use-trigger-shape', 'repository': REPOSITORY,
            'workflow': WORKFLOW, 'generator_commit': after,
            'run_id': env['GITHUB_RUN_ID'], 'run_attempt': '1', 'run_number': '1',
            **value, 'published': False}


def check_selection(selection, marker=MARKER, repo_root='.', env=None):
    trigger = validate_trigger(marker, repo_root, env)
    proof = load(selection)
    require(isinstance(proof, dict) and proof.get('schema') == 'boopa-resolved-inputs-v1' and
            proof.get('repository') == TRACKER, 'Actual resolver proof schema/repository required')
    selected = proof.get('selection')
    require(isinstance(selected, dict) and
            selected.get('selection_authority') == 'authenticated-github-read-and-live-lineage',
            'Actual authenticated resolver selection required')
    require(selected.get('collection_scope') == 'bounded-filtered-search-observation' and
            selected.get('whole_catalog_complete') is False, 'Bounded observation scope required')
    for marker_key, proof_key, selection_key in (
        ('collector_run_id', 'run_id', 'collector_run_id'),
        ('collector_run_attempt', 'run_attempt', 'collector_run_attempt'),
    ):
        require(proof.get(proof_key) == trigger[marker_key] == selected.get(selection_key),
                'Actual selected collector identity differs from the one-use marker: ' + marker_key)
    require(selected.get('tracker_commit') == trigger['collector_saved_commit'],
            'Actual selected saved commit differs from the one-use marker')
    return {'status': 'selection-matches-one-use-marker',
            'tracker_commit': selected['tracker_commit'],
            'collector_run_id': selected['collector_run_id'],
            'collector_run_attempt': selected['collector_run_attempt'],
            'generator_commit': trigger['generator_commit'],
            'published': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate-trigger', 'check-selection'):
        p = sub.add_parser(name)
        p.add_argument('--marker', default=MARKER)
        p.add_argument('--repo-root', default='.')
        p.add_argument('--output')
        if name == 'check-selection':
            p.add_argument('--selection', required=True)
    args = vars(parser.parse_args())
    command = args.pop('command')
    output = args.pop('output')
    result = (validate_trigger if command == 'validate-trigger' else check_selection)(**args)
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if output:
        with Path(output).open('x') as stream:
            stream.write(text)
    print(text, end='')


if __name__ == '__main__':
    main()
