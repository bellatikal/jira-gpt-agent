from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os

app = FastAPI()

class JiraIssue(BaseModel):
    projectKey: str
    summary: str
    description: str
    issueType: str = "Task"

@app.post("/create-jira-issue")
def create_jira_issue(issue: JiraIssue):
    JIRA_EMAIL = os.getenv("JIRA_EMAIL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")  # e.g. https://yourcompany.atlassian.net

    if not (JIRA_EMAIL and JIRA_API_TOKEN and JIRA_BASE_URL):
        raise HTTPException(status_code=500, detail="Missing Jira credentials")

    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    payload = {
        "fields": {
            "project": {"key": issue.projectKey},
            "summary": issue.summary,
            "description": issue.description,
            "issuetype": {"name": issue.issueType}
        }
    }

    response = requests.post(url, json=payload, headers=headers, auth=auth)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    return {
        "issueKey": data.get("key"),
        "issueUrl": f"{JIRA_BASE_URL}/browse/{data.get('key')}"
    }
