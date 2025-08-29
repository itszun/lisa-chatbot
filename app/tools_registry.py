import json
from typing import Dict, Any
from api_client import (
    # HAPUS interactive_login (server tidak butuh)
    # talent
    list_talent, get_talent_detail, create_talent, update_talent, delete_talent,
    # candidates
    list_candidates, get_candidate_detail, create_candidate, update_candidate, delete_candidate,
    # companies
    list_companies, get_company_detail, create_company, update_company, delete_company,
    # company-properties
    list_company_properties, get_company_property_detail, create_company_property, update_company_property, delete_company_property,
    # job-openings
    list_job_openings, get_job_opening_detail, create_job_opening, update_job_opening, delete_job_opening,
)

# ========== DEFINISI TOOLS ==========
tools = [
    # ===== TALENT =====
    {
      "type": "function",
      "function": {
        "name": "list_talent",
        "description": "List talents with optional search & pagination.",
        "parameters": {
          "type": "object",
          "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 10},
            "search": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_talent_detail",
        "description": "Get a talent by ID.",
        "parameters": {
          "type": "object",
          "properties": {"talent_id": {"type": "integer"}},
          "required": ["talent_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_talent",
        "description": "Create a new talent.",
        "parameters": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "position": {"type": "string"},
            "birthdate": {"type": "string", "description": "YYYY-MM-DD"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "educations": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "school": {"type": "string"},
                  "degree": {"type": "string"},
                  "year": {"type": "integer"}
                }
              }
            }
          },
          "required": ["name","position","birthdate","summary"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_talent",
        "description": "Update talent fields.",
        "parameters": {
          "type": "object",
          "properties": {
            "talent_id": {"type": "integer"},
            "name": {"type": "string"},
            "position": {"type": "string"},
            "birthdate": {"type": "string"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "educations": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "school": {"type": "string"},
                  "degree": {"type": "string"},
                  "year": {"type": "integer"}
                }
              }
            }
          },
          "required": ["talent_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_talent",
        "description": "Delete a talent by ID.",
        "parameters": {
          "type": "object",
          "properties": {"talent_id": {"type": "integer"}},
          "required": ["talent_id"]
        }
      }
    },

    # ===== CANDIDATES =====
    {
      "type": "function",
      "function": {
        "name": "list_candidates",
        "description": "List candidates.",
        "parameters": {
          "type": "object",
          "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 10},
            "search": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_candidate_detail",
        "description": "Get candidate by ID.",
        "parameters": {
          "type": "object",
          "properties": {"candidate_id": {"type": "integer"}},
          "required": ["candidate_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_candidate",
        "description": "Create candidate. Needs valid talent_id and job_opening_id.",
        "parameters": {
          "type": "object",
          "properties": {
            "talent_id": {"type": "integer"},
            "job_opening_id": {"type": "integer"},
            "status": {"type": "integer"},
            "regist_at": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
            "interview_schedule": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
            "notified_at": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}
          },
          "required": ["talent_id","job_opening_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_candidate",
        "description": "Update candidate fields.",
        "parameters": {
          "type": "object",
          "properties": {
            "candidate_id": {"type": "integer"},
            "talent_id": {"type": "integer"},
            "job_opening_id": {"type": "integer"},
            "status": {"type": "integer"},
            "regist_at": {"type": "string"},
            "interview_schedule": {"type": "string"},
            "notified_at": {"type": "string"}
          },
          "required": ["candidate_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_candidate",
        "description": "Delete candidate.",
        "parameters": {
          "type": "object",
          "properties": {"candidate_id": {"type": "integer"}},
          "required": ["candidate_id"]
        }
      }
    },

    # ===== COMPANIES =====
    {
      "type": "function",
      "function": {
        "name": "list_companies",
        "description": "List companies.",
        "parameters": {
          "type": "object",
          "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 10},
            "search": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_company_detail",
        "description": "Get company by ID.",
        "parameters": {
          "type": "object",
          "properties": {"company_id": {"type": "integer"}},
          "required": ["company_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_company",
        "description": "Create company.",
        "parameters": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["name"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_company",
        "description": "Update company.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "name": {"type": "string"},
            "description": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["company_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_company",
        "description": "Delete company.",
        "parameters": {
          "type": "object",
          "properties": {"company_id": {"type": "integer"}},
          "required": ["company_id"]
        }
      }
    },

    # ===== COMPANY PROPERTIES =====
    {
      "type": "function",
      "function": {
        "name": "list_company_properties",
        "description": "List company properties.",
        "parameters": {
          "type": "object",
          "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 10},
            "search": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_company_property_detail",
        "description": "Get company property by ID.",
        "parameters": {
          "type": "object",
          "properties": {"prop_id": {"type": "integer"}},
          "required": ["prop_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_company_property",
        "description": "Create company property.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "key": {"type": "string"},
            "value": {"type": "string"}
          },
          "required": ["company_id","key","value"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_company_property",
        "description": "Update company property.",
        "parameters": {
          "type": "object",
          "properties": {
            "prop_id": {"type": "integer"},
            "company_id": {"type": "integer"},
            "key": {"type": "string"},
            "value": {"type": "string"}
          },
          "required": ["prop_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_company_property",
        "description": "Delete company property.",
        "parameters": {
          "type": "object",
          "properties": {"prop_id": {"type": "integer"}},
          "required": ["prop_id"]
        }
      }
    },

    # ===== JOB OPENINGS =====
    {
      "type": "function",
      "function": {
        "name": "list_job_openings",
        "description": "List job openings.",
        "parameters": {
          "type": "object",
          "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 10},
            "search": {"type": "string"}
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "get_job_opening_detail",
        "description": "Get job opening by ID.",
        "parameters": {
          "type": "object",
          "properties": {"opening_id": {"type": "integer"}},
          "required": ["opening_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "create_job_opening",
        "description": "Create job opening.",
        "parameters": {
          "type": "object",
          "properties": {
            "company_id": {"type": "integer"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            "status": {"type": "integer"}
          },
          "required": ["company_id","title"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "update_job_opening",
        "description": "Update job opening.",
        "parameters": {
          "type": "object",
          "properties": {
            "opening_id": {"type": "integer"},
            "company_id": {"type": "integer"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "due_date": {"type": "string"},
            "status": {"type": "integer"}
          },
          "required": ["opening_id"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "delete_job_opening",
        "description": "Delete job opening.",
        "parameters": {
          "type": "object",
          "properties": {"opening_id": {"type": "integer"}},
          "required": ["opening_id"]
        }
      }
    }
]

# ========== MAPPING ==========
available_functions = {
    # talent
    "list_talent": list_talent,
    "get_talent_detail": get_talent_detail,
    "create_talent": create_talent,
    "update_talent": update_talent,
    "delete_talent": delete_talent,
    # candidates
    "list_candidates": list_candidates,
    "get_candidate_detail": get_candidate_detail,
    "create_candidate": create_candidate,
    "update_candidate": update_candidate,
    "delete_candidate": delete_candidate,
    # companies
    "list_companies": list_companies,
    "get_company_detail": get_company_detail,
    "create_company": create_company,
    "update_company": update_company,
    "delete_company": delete_company,
    # company-properties
    "list_company_properties": list_company_properties,
    "get_company_property_detail": get_company_property_detail,
    "create_company_property": create_company_property,
    "update_company_property": update_company_property,
    "delete_company_property": delete_company_property,
    # job-openings
    "list_job_openings": list_job_openings,
    "get_job_opening_detail": get_job_opening_detail,
    "create_job_opening": create_job_opening,
    "update_job_opening": update_job_opening,
    "delete_job_opening": delete_job_opening,
}