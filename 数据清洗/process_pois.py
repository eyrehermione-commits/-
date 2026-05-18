from shapely.ops import unary_union
from shapely.geometry import Point, Polygon, MultiPolygon
import geopandas as gpd
import pandas as pd
import networkx as nx
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
# 强交通吸引力 POI 纯净清洗核心函数
# ==================================================

def clean_pure_pois(input_geojson_path, output_json_path, distance_threshold=10):
    """
    清洗全量强吸引力 POI 数据，基于投影坐标系进行同名 10 米空间邻近去重融合。
    不掺杂任何 building 数据。
    """
    print(f"正在读取全量强吸引力 POI 数据: {input_geojson_path}...")
    
    try:
        gdf = gpd.read_file(input_geojson_path)
    except Exception as e:
        print(f"读取文件失败: {e}")
        return

    # 1. 过滤掉没有名字的噪音数据
    original_count = len(gdf)
    gdf = gdf.dropna(subset=['name'])
    print(f"数据初筛：有名称的有效 POI 实体共 {len(gdf)}/{original_count} 条。")
    
    if len(gdf) == 0:
        print("错误: 筛选后无有效地标数据。")
        return

    # 将 WGS84 投影转换为武汉 UTM 32649（米制坐标），进行绝对精准的物理距离判定
    gdf = gdf.to_crs(epsg=32649)
    print(f"坐标系已投影为米制。开始建立图论网络进行空间聚类融合 (距离阈值: {distance_threshold}米)...")

    final_entities = []
    grouped = gdf.groupby('name')
    total_groups = len(grouped)
    current_group = 0

    # 按名称进行第一层聚类分组（解决重名重合问题）
    for name, group in grouped:
        current_group += 1
        if current_group % 200 == 0 or current_group == total_groups:
            print(f"清洗进度: {current_group}/{total_groups} 组")

        segments = list(group.itertuples())
        
        # 利用 NetworkX 动态构建邻近传递图
        G = nx.Graph()
        for i, seg in enumerate(segments):
            # 双重保险提取原始 ID
            oid = getattr(seg, 'id', None) or (seg.properties.get('id') if hasattr(seg, 'properties') else None) or f"raw_{seg.Index}"
            
            # 收集各类高价值交通决策特征标签
            amenity = getattr(seg, 'amenity', None)
            office = getattr(seg, 'office', None)
            tourism = getattr(seg, 'tourism', None)
            shop = getattr(seg, 'shop', None)
            leisure = getattr(seg, 'leisure', None)
            
            G.add_node(i, geom=seg.geometry, original_id=oid,
                       amenity=amenity, office=office, tourism=tourism,
                       shop=shop, leisure=leisure)
            
        # 计算组内要素之间的物理最短距离
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                try:
                    dist = segments[i].geometry.distance(segments[j].geometry)
                    if dist <= distance_threshold:
                        G.add_edge(i, j)
                except Exception:
                    continue
                    
        # 提取融合后的无重复空间组件（连通子图）
        components = list(nx.connected_components(G))
        
        for idx, comp in enumerate(components):
            comp_geoms = [G.nodes[i]['geom'] for i in comp]
            comp_original_ids = [str(G.nodes[i]['original_id']) for i in comp]
            
            # 收集该实体内部所有的功能标签（进行多源属性融汇）
            amenities = [G.nodes[i]['amenity'] for i in comp if G.nodes[i]['amenity']]
            offices = [G.nodes[i]['office'] for i in comp if G.nodes[i]['office']]
            tourisms = [G.nodes[i]['tourism'] for i in comp if G.nodes[i]['tourism']]
            shops = [G.nodes[i]['shop'] for i in comp if G.nodes[i]['shop']]
            leisures = [G.nodes[i]['leisure'] for i in comp if G.nodes[i]['leisure']]
            
            # 丰富而精准的类型提取优先级逻辑（给与高交通吸引力属性）
            poi_type = "landmark"
            if amenities:
                poi_type = str(amenities[0])  # university, hospital, government, school
            elif offices:
                poi_type = f"office_{offices[0]}"  # company, financial etc.
            elif tourisms:
                poi_type = str(tourisms[0])   # hotel, hostel
            elif shops:
                poi_type = "shopping_mall"    # mall, department_store
            elif leisures:
                poi_type = str(leisures[0])   # park, plaza
                
            # 计算几何重心（Centroid）
            try:
                combined_geom = unary_union(comp_geoms)
                centroid = combined_geom.centroid
            except Exception:
                centroid = comp_geoms[0].centroid
                
            safe_name = str(name)
            entity_id = f"poi_{safe_name}_{idx}".replace(' ', '_').replace('-', '_')
            
            final_entities.append({
                'entity_id': entity_id,
                'name': safe_name,
                'poi_type': poi_type,
                'centroid': centroid,
                'original_ids': comp_original_ids
            })

    # 3. 将物理重心的米制投影坐标重新映射回地理坐标系 WGS84
    result_nodes = []
    if final_entities:
        centroids_geom = [e['centroid'] for e in final_entities]
        entities_gdf = gpd.GeoDataFrame(final_entities, geometry=centroids_geom, crs="EPSG:32649")
        entities_gdf = entities_gdf.to_crs(epsg=4326)
        
        print(f"\n✅ 纯净 POI 清洗大功告成！共提炼出 {len(entities_gdf)} 个具有独立交通价值的 POI 实体节点。")
        
        # 4. 完美组装成兼容前端手写接口的图谱结构
        for idx, row in entities_gdf.iterrows():
            node = {
                "entity_id": row['entity_id'],
                "name": row['name'],
                "label": "POI",  # 纯正的 POI 图谱标签 
                "properties": {
                    "poi_type": row['poi_type'],
                    "lon": round(float(row['geometry'].x), 6),
                    "lat": round(float(row['geometry'].y), 6),
                    "original_ids": row['original_ids']  # 打包所有的原始要素ID，供前端反查高亮
                }
            }
            result_nodes.append(node)

    # 5. 执行高效的手动序列化导出
    try:
        write_json_manually(result_nodes, output_json_path)
        print(f"✅ POI核心图谱数据已落盘: {output_json_path}")
        
        # 打印排名前列的高价值交通型 POI 细分统计
        types_count = {}
        for n in result_nodes:
            pt = n['properties']['poi_type']
            types_count[pt] = types_count.get(pt, 0) + 1
        print("\n交通图谱 POI 组成部分结构分析 (前10名):")
        for pt, count in sorted(types_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   [{pt}]: {count} 个实体")
            
    except Exception as e:
        print(f"最终写入 JSON 失败: {e}")


# ==================================================
# 主函数驱动
# ==================================================

if __name__ == "__main__":
    # 配置好你一键下载的全量 POI 文件
    poi_input = "../pois.geojson"
    output_path = "../data/poi_nodes_final.json"
    
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
        
    clean_pure_pois(
        input_geojson_path=poi_input,
        output_json_path=output_path,
        distance_threshold=10  # 10米阈值足以为同名要素做完美的空间邻近融合
    )