import traceback
import logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

try:
    logger.info("Attempting to import MSGraphService...")
    from ms_graph_service import MSGraphService
    logger.info("Import successful.")

    logger.info("Instantiating MSGraphService...")
    graph_service = MSGraphService()
    logger.info("Instantiation successful.")

    if not graph_service.is_configured:
        logger.error("MSGraphService is not configured. Check your .env file for MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, and MICROSOFT_TENANT_ID.")
    else:
        logger.info("Generating authorization URL...")
        auth_url = graph_service.get_authorization_url()
        logger.info("Authorization URL generation successful.")
        print("\n--- AUTH URL ---")
        print(auth_url)
        print("----------------")

except Exception as e:
    logger.error(f"An error occurred: {e}")
    logger.error(traceback.format_exc())
