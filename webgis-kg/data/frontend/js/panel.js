export function showEntityPanel(
  entity
) {

  const panel =
    document.getElementById(
      "panel"
    );

  const props =
    entity.properties || {};

  let html = `

    <h3>
      ${entity.entity_name}
    </h3>

    <table>
  `;

  Object.entries(props)

    .forEach(([k, v]) => {

      html += `

        <tr>

          <td>
            ${k}
          </td>

          <td>
            ${v}
          </td>

        </tr>
      `;
    });

  html += "</table>";

  panel.innerHTML =
    html;
}