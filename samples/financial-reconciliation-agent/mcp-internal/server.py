import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from uipath import UiPath

mcp = FastMCP(name="Email checker MCP")
csv_file_name = "processed_or_blacklisted_emails-{0}.csv"


def validate_with_check_mail_api(email: str, api_key: str) -> bool:
    import requests
    import json

    url = "https://mailcheck.p.rapidapi.com/"

    querystring = {"disable_test_connection": "true", "domain": email}

    headers = {
        'x-rapidapi-host': "mailcheck.p.rapidapi.com",
        'x-rapidapi-key': api_key
    }

    response = requests.request("GET", url, headers=headers, params=querystring)
    return json.loads(response.text)['block']


def is_temporary_email(email: str) -> bool:
    temp_email_domains = [
        "temp-mail.org", "temp.mail", "disposablemail.com", "tempmail.com",
        "guerrillamail.com", "sharklasers.com", "grr.la", "guerrillamail.info",
        "yopmail.com", "10minutemail.com", "mailinator.com", "throwawaymail.com"
    ]

    domain = email.split('@')[-1].lower()

    return any(temp_domain in domain for temp_domain in temp_email_domains)


@mcp.tool()
async def is_valid_email(email_address: str) -> bool:
    """Verify if email is temporary or not."""
    if check_email_api_key is not None:
        try:
            return not validate_with_check_mail_api(email_address, check_email_api_key)
        except Exception:
            pass
    return not is_temporary_email(email_address)


@mcp.tool()
async def mark_email(email_address: str, base_url: str, status: Literal["refund", "payment"], folder_key: str) -> bool:
    """Mark an email as processed.

    Args:
        email_address (str): The email address to be marked as processed. Example: "user@example.com"
        base_url (str): The base URL of the UiPath cloud service. Example: "https://cloud.uipath.com" (UIPATH_URL)
        status (Literal[str]): The email status. Example: "processed"
        folder_key (str): The folder key of the UiPath cloud service. (UIPATH_FOLDER_KEY)

    Returns:
        bool: True if the email was successfully marked as processed, False if there was an error
    """
    import csv
    from datetime import datetime
    from io import StringIO
    import os
    os.environ['UIPATH_FOLDER_KEY'] = folder_key

    uipath = UiPath(secret=secret, base_url=base_url)

    try:
        current_date = datetime.now().strftime('%Y-%m-%d')
        local_file_path = f"./{csv_file_name.format(current_date)}"

        csv_content = [['email', 'status']]

        try:
            uipath.buckets.download(
                name="stripe",
                blob_file_path=csv_file_name.format(current_date),
                destination_path=local_file_path
            )

            if os.path.exists(local_file_path):
                with open(local_file_path, 'r', newline='') as f:
                    reader = csv.reader(f)
                    csv_content = list(reader)

        except Exception:
            # file might not exist
            pass

        csv_content.append([email_address, status])

        csv_buffer = StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerows(csv_content)

        final_csv_content = csv_buffer.getvalue()
        csv_buffer.close()

        uipath.buckets.upload_from_memory(
            name="stripe",
            content=final_csv_content,
            content_type="text/csv",
            blob_file_path=csv_file_name.format(current_date)
        )

        if os.path.exists(local_file_path):
            os.remove(local_file_path)

        return True

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return False


@mcp.tool()
async def check_same_day_refund(email_address: str, base_url: str, folder_key: str) -> bool:
    """Check if an email has been previously marked as processed.

    Args:
        email_address (str): The email address to check. Example: "user@example.com"
        base_url (str): The base URL of the UiPath cloud service. Example: "https://cloud.uipath.com" (UIPATH_URL)
        folder_key (str): The folder key of the UiPath cloud service. (UIPATH_FOLDER_KEY)

    Returns:
        bool: True if there was already a refund for the email in the same day, False otherwise.
    """
    import csv
    from datetime import datetime
    import os

    os.environ['UIPATH_FOLDER_KEY'] = folder_key
    uipath = UiPath(secret=secret, base_url=base_url)

    current_date = datetime.now().strftime('%Y-%m-%d')
    local_file_path = f"./{csv_file_name.format(current_date)}"

    try:
        uipath.buckets.download(
            name="stripe",
            blob_file_path=csv_file_name.format(current_date),
            destination_path=local_file_path
        )
    except Exception:
        # File might not exist for today
        return False

    result = False
    if os.path.exists(local_file_path):
        try:
            with open(local_file_path, 'r', newline='') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    if row[0] == email_address and row[1] == 'refund':
                        result = True
                        break
        finally:
            os.remove(local_file_path)
        return result

    return result


if __name__ == "__main__":
    mcp.run()
