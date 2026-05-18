from shapely.ops import linemerge, unary_union
from shapely.geometry import LineString, MultiLineString, Point
from collections import Counter
import networkx as nx
import geopandas as gpd
import math

# ==================================================
# 手动 JSON 序列化（完全保留你的原版代码结构）
# ==================================================

def escape_json_string(s):
    """转义 JSON 字符串中的特殊字符"""
    if s is None:
        return "null"
    s = str(s)
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\t', '\\t')
    return s

def format_value(value, indent_level=0):
    """格式化值为 JSON 字符串"""
    indent = "  " * indent_level
    
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return 'null'
        if isinstance(value, float):
            formatted = f"{value:.6f}".rstrip('0').rstrip('.')
            return formatted if formatted else "0"
        return str(value)
    elif isinstance(value, str):
        return f'"{escape_json_string(value)}"'
    elif isinstance(value, (list, tuple)):
        if len(value) == 0:
            return "[]"
        items = [format_value(item, indent_level + 1) for item in value]
        if indent_level > 0:
            return '[\n' + ',\n'.join('  ' * (indent_level + 1) + item for item in items) + '\n' + '  ' * indent_level + ']'
        else:
            return '[' + ', '.join(items) + ']'
    elif isinstance(value, dict):
        if len(value) == 0:
            return "{}"
        items = []
        for k, v in value.items():
            items.append(f'"{escape_json_string(k)}": {format_value(v, indent_level + 1)}')
        if indent_level > 0:
            return '{\n' + ',\n'.join('  ' * (indent_level + 1) + item for item in items) + '\n' + '  ' * indent_level + '}'
        else:
            return '{' + ', '.join(items) + '}'
    else:
        return f'"{escape_json_string(str(value))}"'

def write_json_manually(data, filepath):
    """手动写入 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(format_value(data, 0))

# ==================================================
# 基于站点的地铁方向处理函数
# ==================================================

def process_subways_with_direction(subway_geojson, station_geojson, output_json_path):
    """
    不盲目合并地铁线，通过与地铁站进行空间分析，提取线路的基本属性、涵盖的原始ID以及运营方向
    """
    print(f"正在读取地铁线: {subway_geojson} 和 站点: {station_geojson} ...")
    
    try:
        subway_gdf = gpd.read_file(subway_geojson).dropna(subset=['name'])
        station_gdf = gpd.read_file(station_geojson)
        # 过滤出属于地铁的站点
        if 'railway' in station_gdf.columns:
            station_gdf = station_gdf[station_gdf['railway'] == 'station'].dropna(subset=['name'])
        else:
            station_gdf = station_gdf.dropna(subset=['name'])
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    if len(subway_gdf) == 0 or len(station_gdf) == 0:
        print("错误: 地铁线或地铁站点数据为空")
        return

    # 统一投影到武汉 UTM 投影坐标系计算空间位置
    subway_gdf = subway_gdf.to_crs(epsg=32649)
    station_gdf = station_gdf.to_crs(epsg=32649)

    neo4j_nodes = []
    entity_counter = 0

    # 按地铁名（如 2号线、4号线）分类处理
    for line_name, line_group in subway_gdf.groupby('name'):
        print(f"正在分析: {line_name} ...")
        
        # 1. 收集当前线路涵盖的所有原始路段的 ID
        original_ids = [getattr(seg, 'id', str(seg.Index)) for seg in line_group.itertuples()]
        
        # 2. 将当前线路的所有零碎轨道融合成一条复合几何线，用于计算站点排序
        try:
            line_union = linemerge(unary_union(list(line_group.geometry)))
        except Exception:
            # 如果无法无缝焊接，取其中最长的一段作为主干进行计算
            line_union = max(list(line_group.geometry), key=lambda x: x.length)

        # 3. 找出在这个“地铁轨道”周围 100米 范围内的所有站点
        line_stations = []
        for station in station_gdf.itertuples():
            # 计算站点到地铁轨道的距离
            if station.geometry.distance(line_union) <= 100:
                # 计算站点在整条地铁长线上的“投影距离”（沿线走过的长度）
                proj_dist = line_union.project(station.geometry)
                line_stations.append({
                    'name': str(station.name),
                    'proj_dist': proj_dist
                })
        
        # 4. 根据沿线投影距离排序，得到物理上的站点真实顺序
        line_stations.sort(key=lambda x: x['proj_dist'])
        
        # 5. 提取方向属性（通过排序后的首尾站）
        if len(line_stations) >= 2:
            start_station = line_stations[0]['name']
            end_station = line_stations[-1]['name']
            direction_str = f"{start_station} <-> {end_station}"
        else:
            direction_str = "未知方向（站点数据不足）"
            
        # 6. 计算这条地铁线在洪山区段的重心坐标
        centroid = line_union.centroid
        
        # 7. 反向将重心投影回 WGS84 经纬度，供前端跳转高亮使用
        point_df = gpd.GeoDataFrame(geometry=[centroid], crs="EPSG:32649").to_crs(epsg=4326)
        wgs_centroid = point_df.geometry.iloc[0]
        
        # 8. 构造不丢失任何基本属性的图谱节点实体
        entity_id = f"subway_{line_name}_{entity_counter}".replace(' ', '_').replace('-', '_')
        entity_counter += 1
        
        node = {
            "entity_id": entity_id,
            "name": str(line_name),
            "label": "Subway",
            "properties": {
                "railway": "subway",
                "direction": direction_str,  # 完美的运行方向属性
                "lon": round(wgs_centroid.x, 6),
                "lat": round(wgs_centroid.y, 6),
                "original_ids": original_ids  # 双击前端调用原geojson高亮所需的ID数组
            }
        }
        neo4j_nodes.append(node)

    # 导出 JSON（利用手动拼接序列化，无任何第三方改变）
    try:
        write_json_manually(neo4j_nodes, output_json_path)
        print(f"✅ 完美的地铁方向图谱节点已保存至: {output_json_path}")
        print(f"   节点数量: {len(neo4j_nodes)}")
    except Exception as e:
        print(f"导出 JSON 失败: {e}")


# ==================================================
# 主函数
# ==================================================

if __name__ == "__main__":
    import os
    
    # 请确保这两个下载好的原始 GeoJSON 文件存放在对应位置
    input_subway = "../subways.geojson"
    input_station = "../stations.geojson"
    output_file = "../data/subway_nodes_final.json"
    
    if not os.path.exists(input_subway) or not os.path.exists(input_station):
        print("错误: 请确保 subways.geojson 和 stations.geojson 均存在于 data 目录中")
    else:
        process_subways_with_direction(
            subway_geojson=input_subway,
            station_geojson=input_station,
            output_json_path=output_file
        )