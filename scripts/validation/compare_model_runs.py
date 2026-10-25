"""Compare reproducible RQ outputs, excluding execution timestamps and duration."""
import argparse
import csv
import json
import math
import re
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def compare_runs(reference, candidate, rtol=1e-9, atol=1e-6):
    reference, candidate = Path(reference), Path(candidate)
    differences = []

    def compare(a, b, location):
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a) != set(b):
                differences.append(f'{location}: different keys')
            for key in sorted(set(a) & set(b)):
                compare(a[key], b[key], f'{location}.{key}')
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                differences.append(f'{location}: lengths {len(a)} != {len(b)}')
            for i, (left, right) in enumerate(zip(a, b)):
                compare(left, right, f'{location}[{i}]')
        elif isinstance(a, bool) or isinstance(b, bool):
            if type(a) is not type(b) or a != b:
                differences.append(f'{location}: {a!r} != {b!r}')
        elif a is None or b is None:
            if a != b:
                differences.append(f'{location}: {a!r} != {b!r}')
        else:
            # Counts must match exactly; only continuous estimates get tolerance.
            integer = lambda x: isinstance(x, int) or (isinstance(x, str) and re.fullmatch(r'-?\d+', x))
            if integer(a) and integer(b):
                equal = int(a) == int(b)
            else:
                try:
                    x, y = float(a), float(b)
                    equal = math.isfinite(x) and math.isfinite(y) and math.isclose(x, y, rel_tol=rtol, abs_tol=atol)
                except (ValueError, TypeError):
                    equal = a == b
            if not equal:
                differences.append(f'{location}: {a!r} != {b!r}')

    manifests = [read_json(p/'manifest.json') for p in (reference, candidate)]
    for side, manifest in zip(('reference', 'candidate'), manifests):
        if not manifest.get('all_executed') or any(r['execution'] != 'completed' for r in manifest['models']):
            differences.append(f'{side}: model execution incomplete')
    compare(manifests[0]['config'], manifests[1]['config'], 'config')
    compare([r['rq'] for r in manifests[0]['models']], [r['rq'] for r in manifests[1]['models']], 'selected_models')
    compare(manifests[0]['mode'], manifests[1]['mode'], 'mode')

    def inputs(manifest):
        base = Path(manifest['data_run'])
        return {Path(r['path']).relative_to(base).as_posix():
                {'bytes': r['bytes'], 'sha256': r['sha256']} for r in manifest['input_files']}

    compare(inputs(manifests[0]), inputs(manifests[1]), 'input_identity')
    files = [{p.relative_to(root).as_posix() for p in root.glob('rq*/*')
              if p.name == 'summary.json' or p.suffix == '.csv'} for root in (reference, candidate)]
    if files[0] != files[1]:
        differences.append(f'Output file set differs: {sorted(files[0] ^ files[1])}')
    for name in sorted(files[0] & files[1]):
        if name.endswith('.json'):
            compare(read_json(reference/name), read_json(candidate/name), name)
        else:
            def table(path):
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    return list(csv.DictReader(handle))
            compare(table(reference/name), table(candidate/name), name)
    return {'passed': not differences, 'files_compared': len(files[0] & files[1]),
            'rtol': rtol, 'atol': atol, 'difference_count': len(differences),
            'differences': differences[:25],
            'versions_reference': manifests[0]['versions'], 'versions_candidate': manifests[1]['versions'],
            'note': 'SQLite identity uses audited provenance and size; this does not re-hash the entire database.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    result = compare_runs(args.reference, args.candidate)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(rendered+'\n', encoding='utf8')
    print(rendered)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
