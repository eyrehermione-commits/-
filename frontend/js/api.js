export async function queryNode(
  id
) {

  const res =
    await fetch(

      `http://127.0.0.1:5000/node/${id}`
    );

  return await res.json();
}