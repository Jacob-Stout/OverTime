# ─── Shared Azure Network Infrastructure ─────────────────────────────────────
# This root module manages the Resource Group and Virtual Network that are
# shared across all per-scenario deployments.  Deploy once per environment
# with: overtime network create <spec>

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    managed_by  = "overtime"
    environment = var.environment_name_prefix
  }
}

resource "azurerm_virtual_network" "vnet" {
  name                = var.vnet_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  address_space       = [var.vnet_cidr]

  tags = {
    managed_by  = "overtime"
    environment = var.environment_name_prefix
  }
}
