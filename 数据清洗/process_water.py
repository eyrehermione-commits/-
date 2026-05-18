from shapely.ops import unary_union
from shapely.geometry import Point, Polygon, MultiPolygon
import geopandas as gpd
import pandas as pd
import networkx as nx
import math
import os
from collections import Counter
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
# 水体数据纯净清洗函数
# ==================================================

def clean_waterbodies(input_geojson_path, output_json_path, distance_threshold=20):
    """
    清洗大范围水体数据（面状要素），基于投影坐标系进行同名 20 米空间邻近去重融合。
    """
    print(f"正在读取原始水体要素数据: {input_geojson_path}...")
    
    try:
        gdf = gpd.read_file(input_geojson_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    # 1. 过滤掉没有名字的噪音数据（只要有名字，才是有效的地标水体实体）
    original_count = len(gdf)
    gdf = gdf.dropna(subset=['name'])
    print(f"数据初筛：有名称的有效水体实体共 {len(gdf)}/{original_count} 条。")
    
    if len(gdf) == 0:
        print("错误: 筛选后无有效水体数据。")
        return

    # 将 WGS84 投影转换为武汉 UTM 32649（米制坐标），进行绝对精准的物理距离判定
    gdf = gdf.to_crs(epsg=32649)
    print(f"坐标系已投影为米制。开始建立图论网络进行空间聚类融合 (距离阈值: {distance_threshold}米)...")

    final_entities = []
    grouped = gdf.groupby('name')
    total_groups = len(grouped)
    current_group = 0

    # 按名称进行空间聚类分组（解决长江分段、大湖泊被切碎下载导致的重复实体问题）
    for name, group in grouped:
        current_group += 1
        if current_group % 10 == 0 or current_group == total_groups:
            print(f"水体清洗进度: {current_group}/{total_groups} 组")

        segments = list(group.itertuples())
        
        # 利用 NetworkX 动态构建邻近传递图
        G = nx.Graph()
        for i, seg in enumerate(segments):
            # 双重保险提取原始 ID
            oid = getattr(seg, 'id', None) or (seg.properties.get('id') if hasattr(seg, 'properties') else None) or f"raw_water_{seg.Index}"
            
            # 收集水体类型标签（通常是 waterbody, river, lake）
            water_tag = getattr(seg, 'water', None) or getattr(seg, 'natural', None) or "water"
            
            G.add_node(i, geom=seg.geometry, original_id=oid, water_tag=water_tag)
            
        # 计算组内要素之间的物理最短距离
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                try:
                    dist = segments[i].geometry.distance(segments[j].geometry)
                    if dist <= distance_threshold:
                        G.add_edge(i, j)
                except Exception:
                    continue
                    
        # 提取融合后的无重复空间组件
        components = list(nx.connected_components(G))
        
        for idx, comp in enumerate(components):
            comp_geoms = [G.nodes[i]['geom'] for i in comp]
            comp_original_ids = [str(G.nodes[i]['original_id']) for i in comp]
            comp_tags = [G.nodes[i]['water_tag'] for i in comp]
            
            main_tag = Counter(comp_tags).most_common(1)[0][0]
                
            # 使用空间联合（unary_union）把分段切碎的湖泊或河流多边形融合成整体，并计算完美的几何重心
            try:
                combined_geom = unary_union(comp_geoms)
                centroid = combined_geom.centroid
            except Exception:
                centroid = comp_geoms[0].centroid
                
            safe_name = str(name)
            entity_id = f"water_{safe_name}_{idx}".replace(' ', '_').replace('-', '_')
            
            final_entities.append({
                'entity_id': entity_id,
                'name': safe_name,
                'water_type': main_tag,
                'centroid': centroid,
                'original_ids': comp_original_ids
            })

    # 3. 将物理重心的米制投影坐标重新映射回地理坐标系 WGS84
    result_nodes = []
    if final_entities:
        centroids_geom = [e['centroid'] for e in final_entities]
        entities_gdf = gpd.GeoDataFrame(final_entities, geometry=centroids_geom, crs="EPSG:32649")
        entities_gdf = entities_gdf.to_crs(epsg=4326)
        
        print(f"\n✅ 水体清洗大功告成！共提炼出 {len(entities_gdf)} 个唯一语义的水体地标实体节点。")
        
        # 4. 完美组装成兼容前端手写接口的图谱结构
        for idx, row in entities_gdf.iterrows():
            node = {
                "entity_id": row['entity_id'],
                "name": row['name'],
                "label": "Water",  # 独立的图谱节点标签：Water
                "properties": {
                    "water_type": row['water_type'],
                    "lon": round(float(row['geometry'].x), 6),
                    "lat": round(float(row['geometry'].y), 6),
                    "original_ids": row['original_ids']  # 打包所有的原始要素ID，供前端反查完整湖泊 Polygon 高亮
                }
            }
            result_nodes.append(node)

    # 5. 执行高效的手动序列化导出
    try:
        write_json_manually(result_nodes, output_json_path)
        print(f"✅ 水体核心图谱数据已落盘: {output_json_path}")
            
    except Exception as e:
        print(f"最终写入 JSON 失败: {e}")


# ==================================================
# 主函数驱动
# ==================================================

if __name__ == "__main__":
    # 配置你的输入输出路径
    water_input = "../water.geojson" # 对应我们最开始用 Overpass 扒下来的水系绿地数据
    output_path = "../data/water_nodes_final.json"
    
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
        
    clean_waterbodies(
        input_geojson_path=water_input,
        output_json_path=output_path,
        distance_threshold=20  # 20米阈值足以为大江大湖被切碎的要素做完美的空间无缝焊接
    )