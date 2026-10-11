"""Batch command-line interface."""
import argparse
from pathlib import Path
from engine import MODES, convert

def main():
    parser = argparse.ArgumentParser(description='Convert PDFs to grayscale or bilevel PDFs')
    parser.add_argument('files', type=Path, nargs='+')
    parser.add_argument('-o', '--output', type=Path, default=Path('converted'))
    parser.add_argument('--mode', choices=MODES, default='bw')
    parser.add_argument('--dpi', type=int, default=200)
    parser.add_argument('--allow-larger', action='store_true')
    args = parser.parse_args()
    failed = 0
    for p in args.files:
        try:
            dest = args.output / (p.stem + '_' + args.mode + '.pdf')
            index = 2
            while dest.exists() or dest.resolve() == p.resolve():
                dest = args.output / (p.stem + '_' + args.mode + f'_{index}.pdf')
                index += 1
            result = convert(p, dest, args.mode, args.dpi, not args.allow_larger)
            print(f"{p.name} -> {dest}: {result['old_bytes']:,} -> {result['new_bytes']:,} bytes")
        except Exception as e:
            failed += 1
            print(f'ERROR {p}: {e}')
    return int(failed != 0)

if __name__ == '__main__':
    raise SystemExit(main())
