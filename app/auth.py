from typing import Any, List, Optional
from pydantic import BaseModel
from fastapi_keycloak import FastAPIKeycloak
from fastapi_keycloak.model import HTTPMethod, KeycloakRole
from fastapi_keycloak.api import result_or_error

from app.config import get_settings

settings = get_settings()

class KeycloakClient(BaseModel):
    id: str
    clientId: str
    name: Optional[str]
    description: Optional[str]
    surrogateAuthRequired: bool
    enabled: bool
    alwaysDisplayInConsole: Optional[bool]
    clientAuthenticatorType: str
    redirectUris: List[str]
    webOrigins: List[str]
    notBefore: int
    access: dict
    attributes: Optional[dict]

@result_or_error(response_model=KeycloakClient, is_list=True)
def get_all_clients(self) -> List[KeycloakClient]:
    """Monkeypatched method for getting all clients."""
    return self._admin_request(url=self.admin_uri(resource="clients"), method=HTTPMethod.GET)

@result_or_error(response_model=KeycloakClient, is_list=True)
def get_clients(self, client_names: List[str]) -> List[Any] or None:
    """Monkeypatched method for getting clients."""
    if client_names is None:
        return
    clients = self.get_all_clients()
    return list(filter(lambda client: client.clientId in client_names, clients))

@result_or_error(response_model=KeycloakRole, is_list=True)
def get_client_roles_available(self, user_id: str, client: str) -> dict:
    """Monkeypatched method for getting available client roles."""
    return self._admin_request(
        url=f"{self.users_uri}/{user_id}/role-mappings/clients/{client}/available",
        method=HTTPMethod.GET
    )

@result_or_error()
def add_client_roles_to_user(self, roles: List[str], user_id: str, client: str):
    """Monkeypatched method for adding client roles."""
    keycloak_roles = self.get_client_roles_available(user_id, client)
    roles_to_add = filter(lambda keycloak_role: keycloak_role.name in roles, keycloak_roles)

    self._admin_request(
        url=f"{self.users_uri}/{user_id}/role-mappings/clients/{client}",
        data=[role.__dict__ for role in roles_to_add],
        method=HTTPMethod.POST
    )

FastAPIKeycloak.KeycloakClient = KeycloakClient
FastAPIKeycloak.get_all_clients = get_all_clients
FastAPIKeycloak.get_clients = get_clients
FastAPIKeycloak.get_client_roles_available = get_client_roles_available
FastAPIKeycloak.add_client_roles_to_user = add_client_roles_to_user

idp =  FastAPIKeycloak(
    server_url=settings.keycloak_server_url,
    client_id=settings.keycloak_client_id,
    client_secret=settings.keycloak_client_secret,
    admin_client_secret=settings.keycloak_admin_client_secret,
    realm=settings.keycloak_realm,
    callback_uri=settings.keycloak_callback_uri,
)