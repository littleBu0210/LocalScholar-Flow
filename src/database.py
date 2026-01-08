"""
MongoDB database operations module
Used to replace JSON file for storing paper status
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


class Database:
    """MongoDB database management class"""

    def __init__(self, config_path: str = "./json/config.json"):
        """
        Initialize database connection

        Args:
            config_path: Configuration file path
        """
        self.config = self._load_config(config_path)
        self.mongo_config = self.config.get("mongodb", {})

        # Connect to MongoDB
        self.client = None
        self.db = None
        self.collection = None

        self._connect()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration file"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _connect(self):
        """Connect to MongoDB"""
        try:
            host = self.mongo_config.get("host", "localhost")
            port = self.mongo_config.get("port", 27017)
            database = self.mongo_config.get("database", "paper_flow")
            collection = self.mongo_config.get("collection", "papers")

            # Create client connection
            self.client = MongoClient(
                host=host,
                port=port,
                serverSelectionTimeoutMS=5000
            )

            # Test connection
            self.client.admin.command('ping')

            # Set database and collection
            self.db = self.client[database]
            self.collection = self.db[collection]

            # _id field is unique by default, no need to create index

            print(f"✅ MongoDB connected successfully: {host}:{port}/{database}")

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            print("🔌 MongoDB connection closed")

    def get_paper_state(self, title: str) -> Optional[Dict]:
        """
        Get state of a single paper

        Args:
            title: Paper title

        Returns:
            Paper state dictionary, returns None if not exists
        """
        doc = self.collection.find_one({"_id": title})
        if doc:
            # Remove MongoDB's _id field, return business data
            return {
                "pdf2md": doc.get("pdf2md", False),
                "is_translated": doc.get("is_translated", False)
            }
        return None

    def get_all_states(self) -> Dict[str, Dict]:
        """
        Get state of all papers

        Returns:
            Dictionary with title as key and state dictionary as value
        """
        states = {}
        for doc in self.collection.find():
            title = doc["_id"]
            states[title] = {
                "pdf2md": doc.get("pdf2md", False),
                "is_translated": doc.get("is_translated", False)
            }
        return states

    def update_paper_state(self, title: str, state: Dict):
        """
        Update or insert paper state

        Args:
            title: Paper title
            state: State dictionary containing pdf2md, is_translated
        """
        doc = {
            "_id": title,
            "pdf2md": state.get("pdf2md", False),
            "is_translated": state.get("is_translated", False)
        }
        self.collection.update_one(
            {"_id": title},
            {"$set": doc},
            upsert=True
        )

    def update_multiple_states(self, states: Dict[str, Dict]):
        """
        Batch update paper states

        Args:
            states: Dictionary with title as key and state dictionary as value
        """
        from pymongo import ReplaceOne

        bulk_operations = []
        for title, state in states.items():
            doc = {
                "_id": title,
                "pdf2md": state.get("pdf2md", False),
                "is_translated": state.get("is_translated", False)
            }
            bulk_operations.append(
                ReplaceOne({"_id": title}, doc, upsert=True)
            )

        if bulk_operations:
            self.collection.bulk_write(bulk_operations)

    def delete_paper_state(self, title: str):
        """
        Delete state of a single paper

        Args:
            title: Paper title
        """
        self.collection.delete_one({"_id": title})

    def clear_all_states(self):
        """Clear all state data"""
        self.collection.delete_many({})

    def get_stats(self) -> Dict:
        """
        Get statistics

        Returns:
            Dictionary containing statistics
        """
        total = self.collection.count_documents({})

        stats = {
            "total": total,
            "pdf2md": self.collection.count_documents({"pdf2md": True}),
            "translated": self.collection.count_documents({"is_translated": True})
        }

        return stats

    def __enter__(self):
        """Support with statement"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close connection when exiting with statement"""
        self.close()


# Global database instance (for compatibility with old code)
_db_instance: Optional[Database] = None


def get_database(config_path: str = "./json/config.json") -> Database:
    """
    Get database instance (singleton pattern)

    Args:
        config_path: Configuration file path

    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(config_path)
    return _db_instance


def load_state() -> Dict:
    """
    Compatibility with old code: Load state from MongoDB

    Returns:
        State dictionary
    """
    db = get_database()
    return db.get_all_states()


def save_state(state: Dict):
    """
    Compatibility with old code: Save state to MongoDB

    Args:
        state: State dictionary
    """
    db = get_database()
    db.update_multiple_states(state)
