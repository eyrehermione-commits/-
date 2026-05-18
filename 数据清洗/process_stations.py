from shapely.geometry import Point
import geopandas as gpd
import math
import os

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
# 交通站点处理函数
# ==================================================

def process_stations(input_geojson_path, output_json_path):
    """
    处理交通站点数据，保留基本属性、坐标及原始ID，生成适合 Neo4j 导入的 JSON
    """
    print(f"正在读取交通站点数据: {input_geojson_path}...")
    
    try:
        # 读取原始站点 GeoJSON
        gdf = gpd.read_file(input_geojson_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
    
    # 1. 清洗：去掉没有名字的脏数据（在语义图谱中，无名站点没有检索价值）
    original_count = len(gdf)
    gdf = gdf.dropna(subset=['name'])
    print(f"清洗后: {len(gdf)}/{original_count} 个有名称的站点保留")
    
    if len(gdf) == 0:
        print("错误: 没有有效的站点数据")
        return
    
    neo4j_nodes = []
    
    # 2. 遍历每一个站点点要素，直接提取基本属性
    for idx, row in gdf.iterrows():
        try:
            # 确保几何类型是 Point（如果是多边形，取重心，点状要素直接取几何本身）
            geom = row['geometry']
            if geom.geom_type == 'Point':
                lon, lat = geom.x, geom.y
            else:
                centroid = geom.centroid
                lon, lat = centroid.x, centroid.y
                
            # 3. 双重保险提取原始要素的 ID
            original_id = getattr(row, 'id', None) or (row.properties.get('id') if hasattr(row, 'properties') else None) or f"node_idx_{idx}"
            
            # 4. 识别站点细分类型（用于辅助区分地铁站、公交站）
            # OSM 中地铁站通常标记为 railway=station，公交站通常标记为 highway=bus_stop
            station_type = "unknown"
            if 'railway' in row and row['railway'] == 'station':
                station_type = "subway_station"
            elif 'highway' in row and row['highway'] == 'bus_stop':
                station_type = "bus_stop"
            
            safe_name = str(row['name'])
            # 构造唯一的实体ID
            entity_id = f"station_{safe_name}_{idx}".replace(' ', '_').replace('-', '_')
            
            # 5. 组装节点字典，完美契合前端“双击高亮”与“跳转展示属性”的要求
            node = {
                "entity_id": entity_id,
                "name": safe_name,
                "label": "Station", # 统一标签为 Station
                "properties": {
                    "station_type": station_type, # 基本属性：站点类型
                    "lon": round(float(lon), 6),  # 基本属性：经度
                    "lat": round(float(lat), 6),  # 基本属性：纬度
                    "original_ids": [str(original_id)] # 放入数组中，保持与道路、地铁的数据结构完全一致，方便前端联动
                }
            }
            neo4j_nodes.append(node)
            
        except Exception as e:
            print(f"  警告: 处理第 {idx} 个站点要素时出错: {e}")
            continue

    # 6. 导出 JSON（完全使用手动拼接序列化，无任何第三方改变）
    try:
        write_json_manually(neo4j_nodes, output_json_path)
        print(f"✅ 完美的交通站点图谱节点已保存至: {output_json_path}")
        print(f"   节点数量: {len(neo4j_nodes)}")
        
        # 简单统计站点类型分布
        types_count = {}
        for n in neo4j_nodes:
            st = n['properties']['station_type']
            types_count[st] = types_count.get(st, 0) + 1
        print("站点类型统计:")
        for st, count in types_count.items():
            print(f"   {st}: {count}")
            
    except Exception as e:
        print(f"导出 JSON 失败: {e}")


# ==================================================
# 主函数
# ==================================================

if __name__ == "__main__":
    # 检查输入文件是否存在
    input_file = "../stations.geojson"
    output_file = "../data/station_nodes_final.json"
    
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")
        
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 {input_file}")
    else:
        process_stations(input_file, output_file)