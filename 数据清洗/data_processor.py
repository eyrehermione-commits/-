from shapely.ops import linemerge, unary_union
from shapely.geometry import LineString, MultiLineString
from collections import Counter
import networkx as nx
import geopandas as gpd
import math

# ==================================================
# 手动 JSON 序列化（避免使用 json 模块）
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
        # 处理浮点数精度
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
# 道路处理函数
# ==================================================

def process_roads_spatially(input_geojson_path, output_json_path, distance_threshold=30):
    """
    处理道路数据，进行空间聚类，生成适合 Neo4j 导入的 JSON
    
    参数:
        input_geojson_path: 输入 GeoJSON 文件路径
        output_json_path: 输出 JSON 文件路径
        distance_threshold: 距离阈值（米），默认30米
    """
    
    print(f"正在读取 {input_geojson_path}...")
    
    try:
        gdf = gpd.read_file(input_geojson_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
    
    # 清洗：去掉没有名字的脏数据
    original_count = len(gdf)
    gdf = gdf.dropna(subset=['name'])
    print(f"清洗后: {len(gdf)}/{original_count} 条道路保留")
    
    # 检查是否有数据
    if len(gdf) == 0:
        print("错误: 没有有效的道路数据")
        return
    
    # 【关键步骤1】投影转换：将WGS84经纬度转换为武汉的UTM投影（EPSG:32649）
    # 这样距离计算的单位才是“米”，而不是“度”
    try:
        gdf = gdf.to_crs(epsg=32649)
        print(f"坐标系已投影为米制 (EPSG:32649)")
    except Exception as e:
        print(f"投影转换失败: {e}")
        return
    
    print(f"开始进行空间拓扑聚类分析 (同名且距离 < {distance_threshold}米)...")
    
    final_entities = []
    skipped_count = 0
    
    # 按名字进行初步大分组
    grouped = gdf.groupby('name')
    total_groups = len(grouped)
    current_group = 0
    
    for name, group in grouped:
        current_group += 1
        if current_group % 100 == 0:
            print(f"处理进度: {current_group}/{total_groups} 组")
        
        segments = list(group.itertuples())
        
        # 【关键步骤2】使用 NetworkX 构建空间邻近图
        G = nx.Graph()
        for i, seg in enumerate(segments):
            # 获取 highway 属性，如果不存在则设为 "unknown"
            highway = getattr(seg, 'highway', None) or "unknown"
            
            # 【仅新增：提取该段道路原本的id】
            original_id = getattr(seg, 'id', str(seg.Index))
            
            # 【仅新增：把 original_id 加到图中】
            G.add_node(i, geom=seg.geometry, highway=highway, original_id=original_id) 
        
        # 嵌套循环计算同名路段之间的最小距离
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                try:
                    # 如果两条同名路段距离小于阈值，说明它们是同一条物理道路
                    distance = segments[i].geometry.distance(segments[j].geometry)
                    if distance <= distance_threshold:
                        G.add_edge(i, j)
                except Exception as e:
                    # 几何计算错误，跳过
                    continue
        
        # 【关键步骤3】提取连通子图（分离出同名但在空间上互相独立的道路）
        components = list(nx.connected_components(G))
        
        for idx, comp in enumerate(components):
            try:
                comp_geoms = [G.nodes[i]['geom'] for i in comp]
                comp_highways = [G.nodes[i]['highway'] for i in comp]
                
                # 【仅新增：从这个连通的子图中，提取出所有原始道路碎片的id集合】
                comp_original_ids = [G.nodes[i]['original_id'] for i in comp]
                
                # 将这个簇内的所有线段缝合
                try:
                    unioned = unary_union(comp_geoms)
                    
                    # 根据几何类型处理
                    if unioned.geom_type == 'LineString':
                        merged_geom = unioned
                    elif unioned.geom_type == 'MultiLineString':
                        # 尝试合并
                        merged = linemerge(unioned)
                        if merged.geom_type == 'LineString':
                            merged_geom = merged
                        else:
                            # 如果合并后还不是单线，取最长的那条
                            longest_line = max(unioned.geoms, key=lambda x: x.length)
                            merged_geom = longest_line
                            print(f"  警告: {name} 无法合并为单线，使用最长线段 (长度: {longest_line.length:.1f}m)")
                    else:
                        # 其他类型（Point, Polygon等），取第一个线段
                        print(f"  警告: {name} 包含非线几何类型 {unioned.geom_type}，使用第一个线段")
                        merged_geom = comp_geoms[0]
                except Exception as e:
                    print(f"  警告: 合并 {name} 时出错: {e}，使用第一个线段")
                    merged_geom = comp_geoms[0]
                
                # 取出现频率最高的道路等级
                main_highway = Counter(comp_highways).most_common(1)[0][0]
                
                # 确保 name 是字符串
                safe_name = str(name) if name else "unknown"
                
                # 为区分同名异地实体，在实体ID中加入自增序号
                entity_id = f"road_{safe_name}_{idx}".replace(' ', '_').replace('-', '_')
                
                final_entities.append({
                    'entity_id': entity_id,
                    'name': safe_name,
                    'geometry': merged_geom,
                    'highway': main_highway,
                    'original_ids': comp_original_ids # 【仅新增：存入合并实体】
                })
                
            except Exception as e:
                skipped_count += 1
                print(f"  错误: 处理 {name} 的分组 {idx} 时失败: {e}")
                continue
    
    if len(final_entities) == 0:
        print("错误: 没有生成任何有效的道路实体")
        return
    
    print(f"跳过/失败的片段: {skipped_count}")
    
    # 将聚类后的数据转换回 GeoDataFrame
    result_gdf = gpd.GeoDataFrame(final_entities, crs="EPSG:32649")
    
    # 【关键步骤4】反向投影回 WGS84(EPSG:4326)，提取供前端地图使用的经纬度
    try:
        result_gdf = result_gdf.to_crs(epsg=4326)
        print(f"已转换回 WGS84 坐标系")
    except Exception as e:
        print(f"反向投影失败: {e}")
        return
    
    print(f"空间聚类完成！共生成 {len(result_gdf)} 个具有唯一语义和空间连贯性的道路节点。")
    
    # 提取并格式化为 Neo4j JSON
    neo4j_nodes = []
    for idx, row in result_gdf.iterrows():
        try:
            centroid = row['geometry'].centroid
            
            node = {
                "entity_id": row['entity_id'],
                "name": row['name'],
                "label": "Road",
                "properties": {
                    "highway": row['highway'],
                    "lon": round(centroid.x, 6),
                    "lat": round(centroid.y, 6),
                    "original_ids": row['original_ids'] # 【仅新增：存入属性列表】
                }
            }
            neo4j_nodes.append(node)
        except Exception as e:
            print(f"  处理节点 {idx} 时出错: {e}")
            continue
    
    # 导出 JSON（使用手动方法，避免 json 模块）
    try:
        write_json_manually(neo4j_nodes, output_json_path)
        print(f"✅ 完美的道路图谱节点已保存至: {output_json_path}")
        print(f"  节点数量: {len(neo4j_nodes)}")
        
        # 统计道路类型
        highway_types = {}
        for node in neo4j_nodes:
            htype = node['properties']['highway']
            highway_types[htype] = highway_types.get(htype, 0) + 1
        
        print("\n道路类型统计:")
        for htype, count in sorted(highway_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {htype}: {count}")
            
    except Exception as e:
        print(f"导出 JSON 失败: {e}")
        
        # 备用方案：保存为 CSV
        import csv
        csv_path = output_json_path.replace('.json', '.csv')
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['entity_id', 'name', 'label', 'highway', 'lon', 'lat'])
            for node in neo4j_nodes:
                writer.writerow([
                    node['entity_id'],
                    node['name'],
                    node['label'],
                    node['properties']['highway'],
                    node['properties']['lon'],
                    node['properties']['lat']
                ])
        print(f"✅ 已保存为 CSV 格式: {csv_path}")

# ==================================================
# 主函数
# ==================================================

if __name__ == "__main__":
    import os
    
    # 检查输入文件是否存在
    input_file = "../roads.geojson"
    output_file = "../data/road_nodes_final.json"
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")
    
    if not os.path.exists(input_file):
        print(f"错误: 输入文件不存在 {input_file}")
        print("请确保 roads.geojson 文件在正确的位置")
    else:
        # 执行脚本 (阈值默认30米，足以处理一般的辅道分离或路口断点)
        process_roads_spatially(
            input_geojson_path=input_file,
            output_json_path=output_file,
            distance_threshold=30
        )