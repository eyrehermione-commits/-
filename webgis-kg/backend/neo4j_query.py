from neo4j import GraphDatabase

driver = GraphDatabase.driver(

    "bolt://localhost:7687",

    auth=("neo4j", "12345678")
)

def query_node(node_id):

    with driver.session() as session:

        result = session.run(

            """
            MATCH (n)

            WHERE n.entity_id = $id

            RETURN n
            """,

            id=node_id
        )

        record = result.single()

        if record:

            return dict(
                record["n"]
            )

        return {}