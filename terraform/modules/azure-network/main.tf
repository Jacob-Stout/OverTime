# ─── Data sources (RG + VNet created by terraform/azure-network/) ────────────

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_virtual_network" "vnet" {
  name                = var.vnet_name
  resource_group_name = data.azurerm_resource_group.rg.name
}

# ─── Subnet (per-scenario) ──────────────────────────────────────────────────

resource "azurerm_subnet" "subnet" {
  name                 = var.subnet_name
  resource_group_name  = data.azurerm_resource_group.rg.name
  virtual_network_name = data.azurerm_virtual_network.vnet.name
  address_prefixes     = [var.subnet_cidr]
}

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  SECURITY WARNING — these rules default to source_address "*".     ║
# ║  This is acceptable in an isolated lab VNet with no public IP,     ║
# ║  but MUST be restricted (var.allowed_source_prefix) if the VNet    ║
# ║  is internet-facing or peered with other networks.                 ║
# ╚══════════════════════════════════════════════════════════════════════╝
resource "azurerm_network_security_group" "nsg" {
  name                = "${var.subnet_name}-nsg"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name

  security_rule {
    name                       = "allow-ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-winrm"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5985-5986"
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-rdp"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-intra-vnet"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.vnet_cidr
    destination_address_prefix = var.vnet_cidr
  }

  tags = {
    managed_by  = "overtime"
    environment = var.environment_prefix
  }
}

resource "azurerm_subnet_network_security_group_association" "nsg_assoc" {
  subnet_id                 = azurerm_subnet.subnet.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}
