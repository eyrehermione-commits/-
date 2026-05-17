import {
  initMap
} from "./map.js";

import {
  initGraph
} from "./graph.js";

import {
  initInteraction
} from "./interaction.js";

window.onload = async () => {

  const map =
    await initMap();

  const graph =
    await initGraph();

  initInteraction(
    map,
    graph
  );
};