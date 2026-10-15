# Meta configuration test status

The current build stores each customer's Meta app settings in `client_meta_configs` under the authenticated client ID. Client API endpoints are `GET/PUT /api/clients/meta-config`. The Admin Portal's global Meta configuration form and endpoints were removed from the active UI/API.

Static Python compilation and JavaScript syntax checks are part of the packaging validation. Full pytest/live Meta testing requires the project dependencies, a reachable MongoDB instance, and real Meta app credentials.
