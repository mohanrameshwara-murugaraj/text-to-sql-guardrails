"""Create the synthetic DuckDB dataset: python scripts/build_database.py"""
from pathlib import Path
from text_to_sql.sample_data import build_database
from text_to_sql.schema import get_schema


def main() -> None:
    path = build_database(Path('data/sales.duckdb'))
    print(f'Created database: {path.resolve()}')
    for table, cols in get_schema(path).items():
        print(f'  {table}: {len(cols)} columns')


if __name__ == '__main__':
    main()
