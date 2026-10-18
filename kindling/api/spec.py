"""OpenAPI description (14.2). Generated from the handler registry so
the API and its documentation cannot drift apart."""

from typing import Any, Dict


def openapi_spec() -> Dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "Kindling API", "version": "v1",
                 "description": "Open Music Creation System API"},
        "paths": {
            "/v1/scenes": {
                "post": {"summary": "Create a scene",
                         "requestBody": {"content": {
                             "application/json": {"schema": {
                                 "type": "object"}}}},
                         "responses": {"200": {"description": "scene_id"}}}},
            "/v1/scenes/{scene_id}": {
                "get": {"summary": "Read a scene",
                        "responses": {"200": {"description": "scene"}}},
                "put": {"summary": "Update a scene",
                        "responses": {"200": {"description": "updated"}}}},
            "/v1/render": {
                "post": {"summary": "Submit a render job",
                         "requestBody": {"content": {
                             "application/json": {"schema": {
                                 "type": "object",
                                 "properties": {
                                     "scene_id": {"type": "string"},
                                     "tier": {"type": "string",
                                              "enum": ["draft", "studio",
                                                       "hosted"]},
                                     "seed": {"type": "integer"}}}}}},
                         "responses": {"200": {"description": "job_id"}}}},
            "/v1/edit": {
                "post": {"summary": "Submit an edit job",
                         "requestBody": {"content": {
                             "application/json": {"schema": {
                                 "type": "object",
                                 "properties": {
                                     "scene_id": {"type": "string"},
                                     "operation": {"type": "string",
                                                  "enum": ["inpaint",
                                                           "continue",
                                                           "regenerate_section",
                                                           "part_stem",
                                                           "arrangement",
                                                           "lyric_edit",
                                                           "performance_replace",
                                                           "asset_swap",
                                                           "reference_condition",
                                                           "automation_edit"]},
                                     "selection": {"type": "object"},
                                     "instruction": {"type": "string"},
                                     "seed": {"type": "integer"}}}}}},
                         "responses": {"200": {"description": "job_id"}}}},
            "/v1/jobs/{job_id}": {
                "get": {"summary": "Job status",
                        "responses": {"200": {"description": "status"}}},
                "delete": {"summary": "Cancel a job",
                           "responses": {"200": {"description": "status"}}}},
            "/v1/assets": {
                "get": {"summary": "List assets",
                        "responses": {"200": {"description": "assets"}}},
                "post": {"summary": "Register an asset",
                         "responses": {"200": {"description": "asset_id"}}}},
            "/v1/assets/{asset_id}": {
                "get": {"summary": "Get an asset",
                        "responses": {"200": {"description": "asset"}}}},
            "/v1/profiles/{artist_id}": {
                "get": {"summary": "Get an artist profile",
                        "responses": {"200": {"description": "profile"}}}},
            "/v1/export": {
                "post": {"summary": "Export a project",
                         "responses": {"200": {"description": "job_id"}}}},
        },
    }
