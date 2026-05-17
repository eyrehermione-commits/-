let cy;

let entityMap = {};

export async function initGraph() {

  // =====================
  // 读取实体
  // =====================

  const entityRes =
    await fetch(
      "../data/final_entities.json"
    );

  const entities =
    await entityRes.json();

  // =====================
  // 读取关系
  // =====================

  const relationRes =
    await fetch(
      "../data/final_relations.json"
    );

  const relations =
    await relationRes.json();

  // =====================
  // 只显示 Topology
  // =====================

  const topologyRelations =
    relations.filter(

      r =>
        r.relation_layer ===
        "Topology"
    );

  // =====================
  // 控制规模
  // =====================

  const limitedEntities =
    entities.slice(0, 1000);

  const validIds =
    new Set(

      limitedEntities.map(
        e => e.entity_id
      )
    );

  const limitedRelations =
    topologyRelations.filter(

      r =>
        validIds.has(r.source_id) &&
        validIds.has(r.target_id)
    );

  // =====================
  // 节点
  // =====================

  const nodes =
    limitedEntities.map(e => {

      entityMap[e.entity_id] = e;

      return {

        data: {

          id:
            e.entity_id,

          label:
            e.entity_name,

          type:
            e.entity_type,

          color:
            e.color
        }
      };
    });

  // =====================
  // 边
  // =====================

  const edges =
    limitedRelations.map(r => ({

      data: {

        id:
          `${r.source_id}_${r.target_id}`,

        source:
          r.source_id,

        target:
          r.target_id,

        relation:
          r.relation,

        color:
          r.color
      }
    }));

  // =====================
  // Cytoscape
  // =====================

  cy = cytoscape({

    container:
      document.getElementById(
        "graph"
      ),

    elements: [

      ...nodes,
      ...edges
    ],

    style: [

      // 节点

      {
        selector: "node",

        style: {

          label:
            "data(label)",

          "background-color":
            "data(color)",

          width:
            18,

          height:
            18,

          "font-size":
            8,

          color:
            "#222",

          "text-wrap":
            "wrap",

          "text-max-width":
            80
        }
      },

      // 边

      {
        selector: "edge",

        style: {

          width:
            1,

          "line-color":
            "data(color)",

          opacity:
            0.7,

          "curve-style":
            "bezier"
        }
      }
    ],

    layout: {

      name: "cose",

      animate: true,

      fit: true,

      padding: 30,

      nodeRepulsion:
        500000,

      idealEdgeLength:
        80
    }
  });

  // =====================
  // 双击节点
  // =====================

  let tappedBefore;
  let tappedTimeout;

  cy.on("tap", "node", function(evt) {

    const node = evt.target;

    if (

      tappedTimeout &&
      tappedBefore === node

    ) {

      clearTimeout(
        tappedTimeout
      );

      tappedTimeout = null;

      tappedBefore = null;

      expandNode(node);

    }

    else {

      tappedBefore = node;

      tappedTimeout = setTimeout(
        () => {

          tappedBefore = null;

        },

        300
      );
    }
  });

  return cy;
}

export function getGraph() {

  return cy;
}

export function expandNode(node) {

  const entity =
    entityMap[
      node.id()
    ];

  if (!entity) return;

  // =====================
  // 属性实体化
  // =====================

  const props =
    entity.properties || {};

  Object.entries(props)

    .forEach(([k, v]) => {

      const propId =
        `${node.id()}_${k}`;

      // 已存在
      if (
        cy.getElementById(propId)
          .length > 0
      ) return;

      cy.add({

        group: "nodes",

        data: {

          id:
            propId,

          label:
            `${k}: ${v}`,

          color:
            "#FFD700"
        }
      });

      cy.add({

        group: "edges",

        data: {

          source:
            node.id(),

          target:
            propId,

          color:
            "#999"
        }
      });
    });

  cy.layout({

    name: "cose",

    animate: true

  }).run();

  // =====================
  // 打开属性面板
  // =====================

  import("./panel.js")

    .then(module => {

      module.showEntityPanel(
        entity
      );
    });
}