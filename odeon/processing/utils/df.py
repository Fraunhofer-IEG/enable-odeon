"""
Utils for creating and shaping dataframes and series, mainly those created by
<Object>.to_srs() and <Object>.to_timedf()
"""

from enum import Enum
from typing import Callable, Literal, Any
import pandas as pd
import geopandas as gpd
from pandas.api.types import is_object_dtype
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry


def nested_dict_to_tuple_dict(d: dict, fill_with=None) -> dict:
    """
    Convert a nested dict to a flat dict with tuples as keys. The tuples will
    contain the nesting structure. For values that are less deep nested than
    the deepest nesting, the key tuple will be filled with `fill_with` to match
    the length of the longest tuple.

    Example
    -------
    >>> d = {"a": 1, "b": {"b1": 2, "b2": {"c": 3"}}}
    >>> nested_dict_to_tuple_dict(d=d, fill_with=10)
    {
        ("a", 10, 10): 1,
        ("b", "b1", 10): 2,
        ("b", "b2", "c"): 3
    }
    """

    def inner(d: dict, parents: tuple[str] = None, _depth: int = 1):
        ret = {}
        max_depth = _depth
        parents = parents or []
        for k, v in d.items():
            k = tuple([*parents, k])
            if isinstance(v, dict):
                r, md = inner(v, parents=k, _depth=_depth + 1)
                max_depth = max(md, max_depth)
            else:
                r = {k: v}
            ret |= r
        return ret, max_depth

    d, depth = inner(d=d)
    ret = {}
    for k, v in d.items():
        m = depth - len(k)
        if m > 0:
            k = list(k) + [fill_with for _ in range(m)]
        ret[tuple(k)] = v

    return ret


def fill_index_levels(
    ndfs: list[pd.Series | pd.DataFrame],
    fill_with=None,
    target_depth: int = None,
    axis: Literal[0, 1] = 0,
) -> list[pd.Series | pd.DataFrame]:
    """
    Fill all NDFrames from `ndfs` with a index level count smaller than the
    highest present index level count with additional index levels carrying the
    value `fill_with`. Return in the same order.

    If the target depth is 1, all NDFrames will have a simple Index if no
    MultiIndex is present, or a MultiIndex with one level if at least one
    NDFrame has a MultiIndex.

    Parameters
    ----------
    ndfs : List[Union[pd.Series, pd.DataFrame]]
        The series or dataframes to adjust (can be mixed)
    fill_with : Any
        The value to fill new created index levels with
    target_depth : int, optional
        If given, use this as target depth instead of the highest present. Must
        be >= highest present depth.
    axis : Literal[0, 1]
        0 = Multiindex on columns, 1 = Multiindex on rows
    """
    indices = []
    for idx in ndfs:
        if axis == 1:
            indices.append(idx.columns)
        else:
            indices.append(idx.index)

    # collect the index depth per series:
    any_multiindex = False
    depths = []
    for idx in indices:
        if isinstance(idx, pd.MultiIndex):
            depths.append(len(idx.levels))
            any_multiindex = True
        else:
            depths.append(1)

    # get the target depth:
    if target_depth is None:
        target_depth = max(depths)
    else:
        assert target_depth >= max(depths)

    # list to hold the adjusted indices:
    indices2 = indices.copy()

    # if all series already have the target depth, make sure all are multiindex and return:
    if all(depth == target_depth for depth in depths):
        if any_multiindex:
            for i, idx in enumerate(indices):
                if not isinstance(idx, pd.MultiIndex):
                    idx_df = idx.to_frame()
                    for level in range(1, target_depth):
                        idx_df[level] = fill_with
                    idx = pd.MultiIndex.from_frame(idx_df)
                    indices2[i] = idx

    else:
        # fill the series with lower depth:
        for i, (idx, depth) in enumerate(zip(indices, depths)):
            if target_depth > depth:
                idx_df = idx.to_frame()
                for level in range(depth, target_depth):
                    idx_df[level] = fill_with
                idx = pd.MultiIndex.from_frame(idx_df)
            indices2[i] = idx

    # set the new indices to the original input series/frames:
    ret = []
    for idx, ndf in zip(indices2, ndfs):
        if axis == 1:
            ndf.columns = idx
        else:
            ndf.index = idx
        ret.append(ndf)

    return ret


def fill_and_concat(
    ndfs: list[pd.Series | pd.DataFrame],
    name: str = None,
    keys: list[str] = None,
    drop_key_if_single: bool = False,
) -> pd.Series | pd.DataFrame:
    """
    Transform a list of series with multiindices of different length into
    a concatenated series. For series with a lower multiindex count than the
    highest in `ndfs`, fill added levels with None values. Set the series
    name to `name`.

    Parameters
    ----------
    keys : list[str], optional
        If given, use these as keys for the concatenation (i.e. a prepended
        index level). Length must equal the number of series in `ndfs`.
    drop_key_if_single : bool, optional
        If True and only one series is given in `ndfs`, do not add a key
        level.
    """
    ndfs = fill_index_levels(ndfs=ndfs)
    if len(ndfs) == 1 and drop_key_if_single:
        keys = None

    # remove series that are all-NA or empty:
    non_empty_srs = []
    non_empty_keys = []
    for i, srs in enumerate(ndfs):
        if srs.empty or srs.dropna(how="all").empty:
            continue
        else:
            non_empty_srs.append(srs)
            if keys is not None:
                non_empty_keys.append(keys[i])

    # if all series are empty, return an empty Series
    if not non_empty_srs:
        combi_srs = pd.Series(dtype=float)
        combi_srs.name = name
        return combi_srs

    combi_srs = pd.concat(
        non_empty_srs,
        axis=0,
        keys=non_empty_keys or None,
        names=None,  # don't name the added key level
    )
    combi_srs.name = name
    return combi_srs


def prune_df_multiindex(ndf: pd.DataFrame | pd.Series, remove=[None]) -> pd.DataFrame | pd.Series:
    """
    For a dataframe with row multiindex, remove all index levels that contain
    only values from `remove` or nan.
    """
    idx = ndf.index.remove_unused_levels()
    drops = []
    for i, level in enumerate(idx.levels):
        if all(pd.isna(x) or x in remove for x in idx.levels[i]):
            drops.append(i)
    if drops:
        if len(drops) == len(idx.levels):  # cannot remove all levels
            drops = drops[1:]
        ndf.index = ndf.index.droplevel(drops)
    return ndf


def df_to_filtered_gdf(
    df: pd.DataFrame,
    filter: dict[int, str] | None = None,
    geometry: tuple | int | Any | None = None,
    simplify_column_names: bool = False,
    concat_columns: bool = True,
    concat_column_symbol: str = ", ",
    proj_str: str | None = None,
) -> gpd.GeoDataFrame:
    """
    Convert a DataFrame to a GeoDataFrame by
    - setting the geometry in the column (tuple) `geometry` as active geometry
    - Filtering columns by `filter` (with key as level index, value as string a
    column name at keyed level must match). Number of items in `filter` should
    equal column levels in `df` - 1
    - removing all other geometry columns except `geometry`
    - concatenating column names if a column MultiIndex remains after filtering
    (i.e. length of column levels > `len(filter) + 1` )
    - setting the CRS to `proj_str`

    Parameters
    ----------
    - `geometry`: The column to use as active geometry. Either specified as a
    column index (scalar or tuple), or as the index of the present columns
    containing geometry data

    """

    if geometry is None or isinstance(geometry, int):
        geometry_ = get_geometry_columns(df=df)
        if len(geometry_) == 1:
            geometry = geometry_
        elif len(geometry_) > 1 and isinstance(geometry, int):
            geometry = geometry_[geometry]
        else:
            raise Exception("If no geometry is passed, number of geometry columns must be 1")

    if filter:
        filter = dict(sorted(filter.items(), reverse=True))
        for level, value in filter.items():
            df = df.xs(value, axis=1, level=level, drop_level=True)
        if geometry is not None and not isinstance(geometry, int):
            geometry = [c for i, c in enumerate(geometry) if i not in filter.keys()]

    if simplify_column_names:
        df = map_index_values(df=df, axis=0)

    gsrs = df
    for g in geometry:
        gsrs = gsrs[g]

    if concat_columns:
        if not simplify_column_names:
            df = map_index_values(df=df, axis=0)
        df = multiindexed_ndf_to_concatenated_str_indexed_ndf(
            ndf=df,
            axis=0,
            concat_symbol=concat_column_symbol,
            keep_nan=False,
        )

    df = drop_df_geometries(df)

    gdf = gpd.GeoDataFrame(data=df, geometry=gsrs)
    if proj_str is not None:
        gdf = gdf.set_crs(proj_str)

    return gdf


def simplify_df_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    - transform sets to strings in the form "a, b, c, ..."
    """
    for col in df.columns:
        if is_object_dtype(df[col].dtype):
            # if the above line raises the error that DataFrames don't have dtype attribute, it means that
            # in df, columns are not unique
            first_value = df[col].iloc[0]
            if type(first_value) is set:
                df[col] = df[col].apply(lambda x: f"{', '.join(x)}")
    return df


def remove_trailing_nans(tuples: list[tuple]) -> list[tuple]:
    """
    for a each tuple in `tuples`, remove all trailing Nans
    """
    ret = []
    for tpl in tuples:
        for i in range(len(tpl) - 1, -1, -1):
            if pd.isna(tpl[i]):
                tpl = tpl[0:i]
            else:
                break
        tpl = tuple(tpl)
        ret.append(tpl)
    return ret


def multiindex_to_concatenated_str_index(
    index: pd.Index,
    concat_symbol: str = ", ",
    keep_trailing_nan: bool = False,
    keep_intermediate_nan: bool = False,
) -> pd.Index:
    """
    Create a new Index containing concatenated strings from a MultiIndex `index`.

    Parameters
    ----------
    concat_symbol : str
        The symbol to use for concatenating strings.
    keep_trailing_nan : bool
        If True, keep trailing NaN values in the concatenated strings.
    keep_intermediate_nan : bool
        If True, keep intermediate NaN values in the concatenated strings.
    """

    if isinstance(index, pd.MultiIndex):
        ss = []
        # Work on list of tuples
        tpls: list[tuple] = [*index]

        if not keep_trailing_nan:
            tpls = remove_trailing_nans(tuples=tpls)

        if not keep_intermediate_nan and tpls:
            # Remove any intermediate NaNs/None per tuple (row-wise),
            # independent of whether the column is all-NaN.
            cleaned = []
            for tpl in tpls:
                # If trailing NaNs were already removed above (keep_trailing_nan=False),
                # this will just drop remaining internal NaNs; otherwise we drop all NaNs.
                filtered = tuple(v for v in tpl if not (pd.isna(v) or v is None))
                cleaned.append(filtered)
            tpls = cleaned

        for tpl in tpls:
            tpl = tuple(map(str, tpl))
            s = concat_symbol.join(tpl) if tpl else ""
            ss.append(s)

    elif isinstance(index, pd.Index):
        ss = [str(x) for x in index]
    else:
        raise TypeError("index must be a pd.Index or pd.MultiIndex")
    return pd.Index(ss)


def multiindexed_ndf_to_concatenated_str_indexed_ndf(
    ndf: pd.DataFrame | pd.Series,
    axis: Literal[0, 1] = 0,
    concat_symbol: str = ", ",
    keep_nan: bool = False,
):
    """
    Replace the Multiindex of a DataFrame or Series `df` by an Index containing
    concatenated strings.

    Parameters
    ----------
    axis : Literal[0, 1]
        0 = Multiindex on columns, 1 = Multiindex on rows
    concat_symbol : str
        The symbol to use for concatenating strings.
    keep_nan : bool
        If True, keep trailing NaN values in the concatenated strings.
    """
    if isinstance(ndf, pd.Series):
        srs = True
        ndf = ndf.to_frame()
    else:
        srs = False
        if axis == 0:
            ndf = ndf.T
        else:
            ndf = ndf.copy()

    new_index = multiindex_to_concatenated_str_index(
        index=ndf.index,
        concat_symbol=concat_symbol,
        keep_trailing_nan=keep_nan,
    )
    ndf.index = new_index

    if srs:
        ndf = ndf.squeeze()
    else:
        if axis == 0:
            ndf = ndf.T

    return ndf


def map_index_values(
    df: pd.DataFrame,
    axis: Literal[0, 1] = 0,
    mapper: Callable = None,
) -> pd.DataFrame:
    """
    Applies mapper per value in the index of `df` (possibly Multiindex). If no
    mapper is given, a standard mapper for making everything a string will be
    used.

    Parameters
    ----------
    axis : Literal[0, 1]
        The axis along which to apply the mapper. 0 = Multiindex on columns,
        1 = Multiindex on rows
    """

    def to_str(x):
        if isinstance(x, Enum):
            try:
                return x.value
            except:
                return str(x)
        else:
            return x

    if axis == 1:
        df = df.T

    if mapper is None:
        mapper = to_str
    rename_dict = {}
    for col in df.columns:
        if isinstance(col, tuple):  # = MultiIndex
            rename_dict[col] = tuple([mapper(subcol) for subcol in col])
        else:
            rename_dict[col] = mapper(col)

    # TODO this is complicated, could directly create multiindex from rename_dict.values()
    if isinstance(df.columns, pd.MultiIndex):
        flat = [*df.columns.to_flat_index()]
        flat = [rename_dict[f] for f in flat]
        df.columns = pd.MultiIndex.from_tuples(flat)
    else:
        df = df.rename_axis(mapper=rename_dict, axis=1)

    if axis == 1:
        df = df.T

    return df


def get_geometry_columns(df: pd.DataFrame) -> list:
    """
    Return column address of columns that contain geometries.

    Returns
    -------
    For MultiIndex columns, a list of tuples with column level values. For
    simple columns, a list of column names
    """

    def is_geometry(x):
        return isinstance(x, (BaseGeometry, BaseMultipartGeometry))

    # Try to detect GeoPandas geometry dtype
    def is_geoseries(series: pd.Series) -> bool:
        try:
            import geopandas as _gpd  # noqa: F401

            # Some versions expose .dtype.name == 'geometry'
            return getattr(series.dtype, "name", "") == "geometry"
        except Exception:
            return False

    ret: list[Any] = []
    for column in df.columns:
        s = df[column]
        # Fast path for GeoSeries dtype
        if is_geoseries(s):
            ret.append(column)
            continue

        # Sample first few non-null values to decide
        non_null = s.dropna()
        if non_null.empty:
            # All nulls: treat as non-geometry (cannot prove)
            continue

        # If any non-null is a geometry and there are no non-null non-geometry values, accept
        is_geom_mask = non_null.apply(is_geometry)
        if is_geom_mask.any():
            # Ensure the rest are either geometry or null in original series
            # i.e., avoid mixed types: require all non-null to be geometry
            if is_geom_mask.all():
                ret.append(column)
            else:
                # Mixed types present -> skip
                continue
        # else: no geometry instances among non-null -> skip

    return ret


def has_geometry_columns(df: pd.DataFrame) -> bool:
    """
    Return whether the dataframe has at least one column that contains geometry
    data.
    """
    return len(get_geometry_columns(df=df)) > 0


def drop_df_geometries(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove all geometry columns from DataFrame `df`
    """
    column_tuples = get_geometry_columns(df)
    if column_tuples:
        df = df.drop(column_tuples, axis=1)
    return df
