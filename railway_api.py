import requests
import time
import re

RAILWAY_GRAPHQL = "https://backboard.railway.app/graphql/v2"

def clean_repo(url_or_name: str) -> str:
    text = url_or_name.strip()
    text = re.sub(r'^https?://github\.com/', '', text)
    text = re.sub(r'\.git$', '', text)
    return text.strip('/')

def execute_query(token: str, query: str, variables: dict = None):
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json"
    }
    resp = requests.post(
        RAILWAY_GRAPHQL,
        json={"query": query, "variables": variables or {}},
        headers=headers,
        timeout=30
    )
    if resp.status_code != 200:
        raise Exception(f"خطای سرور Railway (کد {resp.status_code})")
    data = resp.json()
    if "errors" in data and data["errors"]:
        raise Exception(data["errors"][0].get("message", "خطای دسترسی در Railway"))
    return data.get("data", {})

def check_token(token: str):
    """اعتبارسنجی انواع توکن‌های Personal یا Workspace"""
    # روش اول
    try:
        data = execute_query(token, "query { me { id email name } }")
        if data and data.get("me"):
            return data.get("me")
    except Exception:
        pass

    # روش دوم
    try:
        data = execute_query(token, "query { workspaces { id name } }")
        if data and data.get("workspaces"):
            return {"name": "اکانت Railway تایید شده"}
    except Exception:
        pass

    raise Exception("توکن نامعتبر است! لطفاً یک توکن معتبر از بخش Account Tokens ایجاد کنید.")

def get_workspace_id(token: str) -> str:
    queries = [
        "query { me { workspaces { id } } }",
        "query { workspaces { id } }",
        "query { me { teams { id } } }"
    ]
    for q in queries:
        try:
            data = execute_query(token, q)
            me_ws = data.get("me", {}).get("workspaces", []) if "me" in data else []
            if me_ws: return me_ws[0]["id"]
            
            gen_ws = data.get("workspaces", [])
            if gen_ws: return gen_ws[0]["id"]
            
            teams = data.get("me", {}).get("teams", []) if "me" in data else []
            if teams: return teams[0]["id"]
        except Exception:
            continue
    return None

def deploy_panel_flow(token: str, project_name: str, github_repo: str):
    repo = clean_repo(github_repo)
    workspace_id = get_workspace_id(token)

    create_proj_query = """
    mutation CreateProject($name: String!, $workspaceId: String) {
        projectCreate(input: { name: $name, workspaceId: $workspaceId }) {
            id
            name
            environments {
                edges {
                    node {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    variables = {"name": project_name}
    if workspace_id:
        variables["workspaceId"] = workspace_id

    proj_data = execute_query(token, create_proj_query, variables)
    project = proj_data["projectCreate"]
    project_id = project["id"]
    environment_id = project["environments"]["edges"][0]["node"]["id"]

    time.sleep(2)

    create_srv_query = """
    mutation CreateService($projectId: String!, $repo: String!) {
        serviceCreate(input: {
            projectId: $projectId,
            source: {
                repo: $repo
            }
        }) {
            id
            name
        }
    }
    """
    srv_data = execute_query(token, create_srv_query, {
        "projectId": project_id,
        "repo": repo
    })
    service_id = srv_data["serviceCreate"]["id"]

    time.sleep(3)

    create_domain_query = """
    mutation CreateDomain($environmentId: String!, $serviceId: String!) {
        serviceDomainCreate(input: {
            environmentId: $environmentId,
            serviceId: $serviceId
        }) {
            id
            domain
        }
    }
    """
    domain_name = ""
    for _ in range(5):
        try:
            domain_data = execute_query(token, create_domain_query, {
                "environmentId": environment_id,
                "serviceId": service_id
            })
            domain_name = domain_data["serviceDomainCreate"]["domain"]
            if domain_name:
                break
        except Exception:
            time.sleep(2)

    return {
        "project_id": project_id,
        "project_name": project_name,
        "service_id": service_id,
        "domain": domain_name if domain_name else "در حال راه‌اندازی...",
        "repo": repo
    }

def delete_project_api(token: str, project_id: str):
    query = """
    mutation DeleteProject($id: String!) {
        projectDelete(id: $id)
    }
    """
    return execute_query(token, query, {"id": project_id})
