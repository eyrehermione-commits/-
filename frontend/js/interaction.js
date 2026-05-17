import {
  highlightEntityOnMap,
  zoomToEntity
} from "./map.js";

import {
  getGraph
} from "./graph.js";

export function initInteraction() {

  const cy =
    getGraph();

  // =====================
  // 图谱点击
  // =====================

  cy.on(

    "dbltap",

    "node",

    function(evt) {

      const node =
        evt.target;

      const id =
        node.id();

      zoomToEntity(id);

      highlightEntityOnMap(id);
    }
  );
}