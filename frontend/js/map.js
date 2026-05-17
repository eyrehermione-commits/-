let map;

let roadsLayer;
let subwayLayer;
let stationsLayer;
let poiLayer;
let districtLayer;

let entityLayerMap = {};

export async function initMap() {

  // =====================
  // 初始化地图
  // =====================

  map = L.map("map").setView(

    [30.5928, 114.3055],

    12
  );

  // =====================
  // 底图
  // =====================

  L.tileLayer(

    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",

    {

      attribution:
        "&copy; OpenStreetMap"
    }

  ).addTo(map);

  // =====================
  // 行政区
  // =====================

  const districtRes =
    await fetch(
      "../data/wuhan.geojson"
    );

  const districts =
    await districtRes.json();

  districtLayer = L.geoJSON(

    districts,

    {

      style: {

        color:
          "#888",

        weight:
          1,

        fillOpacity:
          0.1
      }
    }

  ).addTo(map);

  // =====================
  // POI
  // =====================

  const poiRes =
    await fetch(
      "../data/wuhan_poi.geojson"
    );

  const pois =
    await poiRes.json();

  poiLayer = L.geoJSON(

    pois,

    {

      pointToLayer:
        (feature, latlng) => {

          const marker =
            L.circleMarker(

              latlng,

              {

                radius:
                  4,

                color:
                  "#0088ff",

                fillColor:
                  "#0088ff",

                fillOpacity:
                  1
              }
            );

          bindEntityEvents(
            marker,
            feature
          );

          return marker;
        }
    }

  ).addTo(map);

  // =====================
  // 站点
  // =====================

  const stationRes =
    await fetch(
      "../data/wuhan_stations.geojson"
    );

  const stations =
    await stationRes.json();

  stationsLayer = L.geoJSON(

    stations,

    {

      pointToLayer:
        (feature, latlng) => {

          const marker =
            L.circleMarker(

              latlng,

              {

                radius:
                  4,

                color:
                  "#ff0000",

                fillColor:
                  "#ff0000",

                fillOpacity:
                  1
              }
            );

          bindEntityEvents(
            marker,
            feature
          );

          return marker;
        }
    }

  ).addTo(map);

  // =====================
  // 道路
  // 默认不显示
  // =====================

  const roadsRes =
    await fetch(
      "../data/wuhan_roads.geojson"
    );

  const roads =
    await roadsRes.json();

  roadsLayer = L.geoJSON(

    roads,

    {

      style: {

        color:
          "#ff8800",

        weight:
          1
      },

      onEachFeature:
        (feature, layer) => {

          bindEntityEvents(
            layer,
            feature
          );
        }
    }
  );

  // =====================
  // 地铁
  // 默认不显示
  // =====================

  const subwayRes =
    await fetch(
      "../data/wuhan_subway.geojson"
    );

  const subway =
    await subwayRes.json();

  subwayLayer = L.geoJSON(

    subway,

    {

      style: {

        color:
          "#0066ff",

        weight:
          2
      },

      onEachFeature:
        (feature, layer) => {

          bindEntityEvents(
            layer,
            feature
          );
        }
    }
  );

  // =====================
  // 展开交通要素按钮
  // =====================

  document

    .getElementById(
      "toggleRoads"
    )

    .onclick = () => {

      roadsLayer.addTo(map);

      subwayLayer.addTo(map);
    };

  return map;
}

// =========================
// 地图事件
// =========================

function bindEntityEvents(
  layer,
  feature
) {

  const props =
    feature.properties || {};

  const entityId =

    props.id ||
    props["@id"] ||
    props.name;

  entityLayerMap[
    entityId
  ] = layer;

  // =====================
  // 单击
  // =====================

  layer.on(

    "click",

    () => {

      import("./panel.js")

        .then(module => {

          module.showEntityPanel({

            entity_name:
              props.name,

            properties:
              props
          });
        });
    }
  );

  // =====================
  // 双击
  // =====================

  layer.on(

    "dblclick",

    () => {

      highlightLayer(layer);

      map.fitBounds(

        layer.getBounds
          ? layer.getBounds()
          : L.latLngBounds([
              layer.getLatLng()
            ])
      );
    }
  );

  // =====================
  // 右键菜单
  // =====================

  layer.on(

    "contextmenu",

    e => {

      import("./menu.js")

        .then(module => {

          module.createContextMenu(

            e.originalEvent.pageX,

            e.originalEvent.pageY,

            props
          );
        });
    }
  );
}

// =========================
// 高亮
// =========================

function highlightLayer(
  layer
) {

  if (layer.setStyle) {

    layer.setStyle({

      color:
        "#ffff00",

      weight:
        5
    });
  }

  else if (
    layer.setRadius
  ) {

    layer.setRadius(10);
  }
}

// =========================
// 外部调用
// =========================

export function zoomToEntity(
  entityId
) {

  const layer =
    entityLayerMap[
      entityId
    ];

  if (!layer) return;

  if (
    layer.getBounds
  ) {

    map.fitBounds(
      layer.getBounds()
    );
  }

  else if (
    layer.getLatLng
  ) {

    map.setView(

      layer.getLatLng(),

      16
    );
  }
}

export function highlightEntityOnMap(
  entityId
) {

  const layer =
    entityLayerMap[
      entityId
    ];

  if (!layer) return;

  highlightLayer(layer);
}