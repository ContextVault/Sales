"""
Neo4j Service - Graph Database Connection Layer

Manages Neo4j connection lifecycle, schema creation, and health checks.
Provides session context management for graph operations.
"""
import os
import logging
from typing import Optional
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)


class Neo4jService:
    """
    Neo4j connection service.
    
    Handles:
    - Connection management with automatic reconnection
    - Schema creation (constraints + indexes)
    - Health checks and statistics
    """
    
    def __init__(self):
        """Initialize Neo4j connection from environment variables."""
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        
        self.driver: Optional[Driver] = None
        self._connected = False
        
        # Try to connect
        self._connect()
    
    def _connect(self):
        """Establish connection to Neo4j."""
        if not self.password:
            logger.warning("NEO4J_PASSWORD not set, skipping connection")
            return
        
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # Verify connection
            self.driver.verify_connectivity()
            self._connected = True
            logger.info(f"Neo4j connection established: {self.uri}")
            
            # Create schema on successful connection
            self._create_schema()
            
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._connected = False
    
    @contextmanager
    def get_session(self):
        """
        Context manager for Neo4j sessions.
        
        Usage:
            with neo4j_service.get_session() as session:
                session.run("MATCH (n) RETURN n LIMIT 10")
        """
        if not self.driver:
            raise ConnectionError("Neo4j driver not initialized")
        
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def _create_schema(self):
        """
        Create constraints and indexes for the graph schema.
        
        Constraints ensure uniqueness and data integrity.
        Indexes speed up queries on common lookup fields.
        """
        if not self._connected:
            return
        
        with self.get_session() as session:
            # Uniqueness constraints
            constraints = [
                "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (d:Decision) REQUIRE d.id IS UNIQUE",
                "CREATE CONSTRAINT person_email IF NOT EXISTS FOR (p:Person) REQUIRE p.email IS UNIQUE",
                "CREATE CONSTRAINT policy_version IF NOT EXISTS FOR (p:Policy) REQUIRE p.version IS UNIQUE",
                "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE",
                "CREATE CONSTRAINT customer_name IF NOT EXISTS FOR (c:Customer) REQUIRE c.name IS UNIQUE"
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                    constraint_name = constraint.split("CONSTRAINT ")[1].split(" IF")[0]
                    logger.debug(f"Created constraint: {constraint_name}")
                except Exception as e:
                    logger.debug(f"Constraint creation skipped (may exist): {e}")
            
            # Performance indexes
            indexes = [
                "CREATE INDEX decision_timestamp IF NOT EXISTS FOR (d:Decision) ON (d.timestamp)",
                "CREATE INDEX decision_type IF NOT EXISTS FOR (d:Decision) ON (d.type)",
                "CREATE INDEX decision_customer IF NOT EXISTS FOR (d:Decision) ON (d.customer_name)",
                "CREATE INDEX decision_industry IF NOT EXISTS FOR (d:Decision) ON (d.customer_industry)",
                "CREATE INDEX decision_outcome IF NOT EXISTS FOR (d:Decision) ON (d.outcome)",
                "CREATE INDEX person_role IF NOT EXISTS FOR (p:Person) ON (p.role)"
            ]
            
            for index in indexes:
                try:
                    session.run(index)
                    index_name = index.split("INDEX ")[1].split(" IF")[0]
                    logger.debug(f"Created index: {index_name}")
                except Exception as e:
                    logger.debug(f"Index creation skipped (may exist): {e}")
            
            logger.info("Neo4j schema initialized (constraints + indexes)")
    
    def health_check(self) -> bool:
        """Check if Neo4j is accessible and responding."""
        if not self.driver or not self._connected:
            return False
        
        try:
            with self.get_session() as session:
                result = session.run("RETURN 1 as health")
                return result.single()["health"] == 1
        except Exception as e:
            logger.error(f"Neo4j health check failed: {e}")
            return False
    
    def get_stats(self) -> dict:
        """
        Get database statistics.
        
        Returns:
            dict with node counts by label and total relationships
        """
        if not self._connected:
            return {"error": "Not connected", "nodes": {}, "relationships": 0}
        
        with self.get_session() as session:
            node_counts = {}
            labels = ["Decision", "Person", "Policy", "Evidence", "Customer"]
            
            for label in labels:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) as count")
                node_counts[label.lower()] = result.single()["count"]
            
            # Count all relationships
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            relationship_count = result.single()["count"]
            
            return {
                "nodes": node_counts,
                "relationships": relationship_count,
                "total_nodes": sum(node_counts.values())
            }
    
    def is_connected(self) -> bool:
        """Check if Neo4j connection is established."""
        return self._connected
    
    def close(self):
        """Close Neo4j connection gracefully."""
        if self.driver:
            self.driver.close()
            self._connected = False
            logger.info("Neo4j connection closed")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

neo4j_service = Neo4jService()
