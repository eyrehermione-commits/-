export function createContextMenu(
  x,
  y,
  entity
) {

  removeMenu();

  const menu =
    document.createElement("div");

  menu.id =
    "contextMenu";

  menu.style.left =
    `${x}px`;

  menu.style.top =
    `${y}px`;

  menu.innerHTML = `

    <div class="menu-item">
      属性
    </div>

    <div class="menu-item">
      空间关系
    </div>

    <div class="menu-item">
      方位关系
    </div>

    <div class="menu-item">
      拓扑关系
    </div>
  `;

  document.body.appendChild(
    menu
  );
}

export function removeMenu() {

  const old =
    document.getElementById(
      "contextMenu"
    );

  if (old) {

    old.remove();
  }
}