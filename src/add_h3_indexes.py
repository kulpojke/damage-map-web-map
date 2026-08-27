#!/usr/bin/env python
'''Add H3 index columns to building GeoJSON data.'''

from __future__ import annotations

import argparse
from pathlib import Path
import site
import sys

user_site = site.getusersitepackages()
if isinstance(user_site, str):
    user_site = [user_site]
sys.path = [
    path for path in sys.path
    if path not in user_site and not path.startswith(f'{site.USER_BASE}/')
]

import geopandas as gpd
import h3
import pandas as pd


DEFAULT_INPUT = Path('data/building_with_inference.geojson')
DEFAULT_OUTPUT = Path('data/buildings_h3.geojson')
DEFAULT_RESOLUTIONS = '5,6,7,8,9,10'


def parse_resolutions(value: str) -> list[int]:
    '''Parse a comma-separated H3 resolution list.'''
    resolutions = [int(part.strip()) for part in value.split(',') if part.strip()]
    invalid = [resolution for resolution in resolutions if resolution < 0 or resolution > 15]
    if invalid:
        raise argparse.ArgumentTypeError(
            f'H3 resolutions must be between 0 and 15: {invalid}'
        )
    return resolutions


def read_buildings(paths: list[Path]) -> gpd.GeoDataFrame:
    '''Read and combine one or more building files.'''
    frames = []
    for path in paths:
        frame = gpd.read_file(path)
        if frame.crs is None:
            frame = frame.set_crs('EPSG:4326')
        frames.append(frame.to_crs('EPSG:4326'))

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs='EPSG:4326')


def add_h3_columns(
    buildings: gpd.GeoDataFrame,
    resolutions: list[int],
) -> gpd.GeoDataFrame:
    '''Add one H3 cell column for each requested resolution.'''
    buildings = buildings.copy()
    points = buildings.geometry.representative_point()
    valid_points = ~(points.is_empty | points.isna())

    for resolution in resolutions:
        column = f'h3_r{resolution}'
        buildings[column] = None
        buildings.loc[valid_points, column] = [
            h3.latlng_to_cell(point.y, point.x, resolution)
            for point in points.loc[valid_points]
        ]

    return buildings


def dedupe_buildings(
    buildings: gpd.GeoDataFrame,
    dedupe_field: str | None,
) -> gpd.GeoDataFrame:
    '''Drop duplicate rows, keeping the last copy of each building.'''
    if not dedupe_field:
        return buildings

    if dedupe_field not in buildings.columns:
        raise ValueError(f'Cannot dedupe: field does not exist: {dedupe_field}')

    return buildings.drop_duplicates(subset=dedupe_field, keep='last')


def write_geojson(buildings: gpd.GeoDataFrame, output_path: Path) -> None:
    '''Write processed buildings as GeoJSON.'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    buildings.to_file(output_path, driver='GeoJSON')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Add H3 index columns to building GeoJSON data.'
    )
    parser.add_argument(
        '--input',
        nargs='+',
        type=Path,
        default=[DEFAULT_INPUT],
        help=f'Input building GeoJSON file(s). Default: {DEFAULT_INPUT}',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f'Output GeoJSON file. Default: {DEFAULT_OUTPUT}',
    )
    parser.add_argument(
        '--resolutions',
        type=parse_resolutions,
        default=parse_resolutions(DEFAULT_RESOLUTIONS),
        help=f'Comma-separated H3 resolutions. Default: {DEFAULT_RESOLUTIONS}',
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite the output instead of appending to it when it exists.',
    )
    parser.add_argument(
        '--dedupe-field',
        default='id',
        help='Field used to dedupe appended data. Use an empty string to disable.',
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_paths = list(args.input)
    if args.output.exists() and not args.overwrite:
        input_paths = [args.output, *input_paths]

    buildings = read_buildings(input_paths)
    buildings = dedupe_buildings(buildings, args.dedupe_field or None)
    buildings = add_h3_columns(buildings, args.resolutions)
    write_geojson(buildings, args.output)

    print(
        f'Wrote {len(buildings):,} buildings with '
        f'{len(args.resolutions)} H3 index columns to {args.output}'
    )


if __name__ == '__main__':
    main()
