# Database file paths
BIRD_DEV_folder = "../BIRD/BIRD_dev/dev_20240627/dev_databases/dev_databases"
BIRD_DEV_OVERVIEW = "../BIRD/BIRD_dev/dev_20240627/dev_tables.json"
BIRD_TRAIN_folder = "../BIRD/BIRD_train/train/train_databases/train_databases"
BIRD_TRAIN_OVERVIEW = "../BIRD/BIRD_train/train/train_tables.json"

SPIDER_TRAIN_folder = '../spider_data/spider_data/database'
SPIDER_DEV_folder = '../spider_data/spider_data/database'
SPIDER_TEST_folder = '../spider_data/spider_data/test_database'

EDGE_SCHEMA_PATH = "edge_schema_files"
EVERY_TABLE_DESC_PATH = "database_description"
EXPORTED_CSV_PATH = "exported_csv_tables"
EXPORTED_SCHEMA_PATH = "exported_table_schemas"
IMPORT_GRAPH_DATA_PATH = "import_graph_data"
FK_RELATION_PATH = "fk_relation_files"

# LLM
# MODEL = 'deepseek-ai/DeepSeek-R1'
MODEL = 'deepseek-reasoner'
Qwen_Embedding_MODEL = "text-embedding-v3"


# DB
REMOTE_DB_HOST = "<YOUR_REMOTE_DB_HOST>"

# Neo4j configuration
NEO4j_PORT = '7687'
NEO4j_BROWSER_PORT = '7687'
NEO4j_INSERT_BATCH_SIZE = 500  # Batch size per insert
# NEO4j_MAX_WORKERS = 4  # Max concurrent worker threads (reduces deadlock risk)
NEO4j_MAX_CONCURRENT_COROUTINES = 4  # Max concurrent coroutines
# NEO4j_TRANSACTION_TIMEOUT = 30  # Transaction timeout (seconds)
NEO4j_DEADLOCK_RETRY_COUNT = 200  # Deadlock retry count
NEO4j_TRANSACTION_DELAY = 0.5  # Delay between transactions (seconds); gives Neo4j time to release memory
NEO4jUSERNAME = "<YOUR_NEO4J_USERNAME>"
NEO4jPASSWORD = "<YOUR_NEO4J_PASSWORD>"

NEO4jUSERNAME_remote = "<YOUR_NEO4J_REMOTE_USERNAME>"
NEO4jPASSWORD_remote = "<YOUR_NEO4J_REMOTE_PASSWORD>"
NEO4j_remote_uri = "<YOUR_NEO4J_REMOTE_URI>"

# Nebula Graph configuration
NEBULA_PORT = 7788  # Nebula Graph port
NEBULA_USERNAME = "<YOUR_NEBULA_USERNAME>"
NEBULA_PASSWORD = "<YOUR_NEBULA_PASSWORD>"
NEBULA_INSERT_BATCH_SIZE = 100  # Batch size per insert
NEBULA_MAX_CONCURRENT_COROUTINES = 4  # Max concurrent coroutines
NEBULA_DEADLOCK_RETRY_COUNT = 200  # Deadlock retry count
NEBULA_TRANSACTION_DELAY = 0.5  # Delay between transactions (seconds)
NEBULA_SESSION_POOL_SIZE = 256  # Session pool size (must be >= max concurrency; 1.5-2x recommended)
NEBULA_THREAD_POOL_WORKERS = 32  # Thread pool size (ThreadPoolExecutor max_workers)
NEBULA_ASYNC_SEMAPHORE = 32  # Async concurrency (asyncio.Semaphore; must be <= NEBULA_SESSION_POOL_SIZE)

# OS
FILEPATH_SPLIT = "/"  # Linux: /; Windows: \\


# SQL2GQL
BIRD_DEV_SQL_folder = "../BIRD/BIRD_dev/dev_20240627"  # Folder containing BIRD SQL files
BIRD_DEV_SQL_file = ["dev.json", "dev_tied_append.json"]
BIRD_TRAIN_SQL_folder = "../BIRD/BIRD_train/train"
BIRD_TRAIN_SQL_file = "train.json"

BIRD_DB_ID_FIELD = "db_id"  # JSON field name
BIRD_SQL_FIELD = "SQL"  # JSON field name

SPIDER_TRAIN_SQL_folder = '../spider_data/spider_data'
SPIDER_TRAIN_SQL_file = ['train_others.json', 'train_spider.json', 'dev.json']
SPIDER_DEV_SQL_folder = SPIDER_TRAIN_SQL_folder
SPIDER_DEV_SQL_file = 'dev.json'
SPIDER_TEST_SQL_folder = SPIDER_TRAIN_SQL_folder
SPIDER_TEST_SQL_file = "test.json"

SPIDER_DB_ID_FIELD = "db_id"
SPIDER_SQL_FIELD = "query"

CYPHER_TRANSLATOR_PATH = "../Translator/neo4j"

GQL_FIELD = "GQL"
