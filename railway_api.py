import requests
import time
import re

RAILWAY_GRAPHQL = "https://backboard.railway.app/graphql/v2"

def clean_repo(url_or_name: str) -> str:
    """تبدیل انواع آدرس گیت‌هاب به فرمت owner/repo"""
    text = url_or_name.strip()
    text = re.sub(r'^https?://github\.com/', '', text)
    text = re.sub(r'\.git$', '', text)
    return text.strip('/')

def execute_query(token: str, query: str, variables: dict = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    resp = requests.post(
        RAILWAY_GRAPHQL,
        json={"query": query, "variables": variables or {}},
        headers=headers,
        timeout=30
    )
    if resp.status_code != 200:
        raise Exception(f"خطای ارتباط با سرور Railway (کد {resp.status_code})")
    
    data = resp.json()
    if "errors" in data and data["errors"]:
        error_msg = data["errors"][0].get("message", "خطای ناشناخته در Railway")
        raise Exception(error_msg)
    return data.get("data", {})

def get_workspace_id(token: str) -> str:
    """دریافت شناسه فضای کاری (Workspace ID) کاربر"""
    # روش اول: دریافت مستقیم از me.workspaces
    q1 = """
    query {
        me {
            id
            workspaces {
                id
                name
            }
        }
    }
    """
    try:
        data = execute_query(token, q1)
        workspaces = data.get("me", {}).get("workspaces", [])
        if workspaces and len(workspaces) > 0:
            return workspaces[0]["id"]
    except Exception:
        pass

    # روش دوم: دریافت از لیست عمومی workspaces
    q2 = """
    query {
        workspaces {
            id
            name
        }
    }
    """
    try:
        data = execute_query(token, q2)
        workspaces = data.get("workspaces", [])
        if workspaces and len(workspaces) > 0:
            return workspaces[0]["id"]
    except Exception:
        pass

    # روش سوم: حساب‌های قدیمی (teams)
    q3 = """
    query {
        me {
            teams {
                id
                name
            }
        }
    }
    """
    try:
        data = execute_query(token, q3)
        teams = data.get("me", {}).get("teams", [])
        if teams and len(teams) > 0:
            return teams[0]["id"]
    except Exception:
        pass

    return None

def check_token(token: str):
    """بررسی اعتبار توکن کاربر"""
    query = """
    query {
        me {
            id
            email
            name
        }
    }
    """
    data = execute_query(token, query)
    return data.get("me")

def deploy_panel_flow(token: str, project_name: str, github_repo: str):
    """فرآیند کامل ساخت پروژه، اتصال به گیت‌هاب و دریافت دامنه"""
    repo = clean_repo(github_repo)

    # دریافت شناسه Workspace کاربر
    workspace_id = get_workspace_id(token)

    # ۱. ساخت پروژه با ارسال workspaceId
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

    # ۲. ساخت سرویس متصل به ریپازیتوری
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

    # چند ثانیه وقفه برای اعمال سرویس
    time.sleep(3)

    # ۳. دریافت خودکار دامنه رایگان Railway
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
        "domain": domain_name if domain_name else "در حال ایجاد دامنه...",
        "repo": repo
    }

def delete_project_api(token: str, project_id: str):
    """حذف کامل پروژه از Railway"""
    query = """
    mutation DeleteProject($id: String!) {
        projectDelete(id: $id)
    }
    """
    return execute_query(token, query, {"id": project_id})
