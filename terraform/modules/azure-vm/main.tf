# ─── Public IP (optional) ─────────────────────────────────────────────────────

resource "azurerm_public_ip" "pip" {
  count               = var.assign_public_ip ? 1 : 0
  name                = "${var.name}-pip"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    managed_by  = "overtime"
    environment = var.environment_prefix
    role        = var.role
  }
}

# ─── Network Interface ────────────────────────────────────────────────────────

resource "azurerm_network_interface" "nic" {
  name                = "${var.name}-nic"
  location            = var.location
  resource_group_name = var.resource_group_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = var.subnet_id
    private_ip_address_allocation = "Static"
    private_ip_address            = var.private_ip_address
    public_ip_address_id          = var.assign_public_ip ? azurerm_public_ip.pip[0].id : null
  }

  tags = {
    managed_by  = "overtime"
    environment = var.environment_prefix
    role        = var.role
  }
}

# NSG is attached at the subnet level by the azure-network module.
# No NIC-level NSG association is needed.

# ─── Linux VM ─────────────────────────────────────────────────────────────────

resource "azurerm_linux_virtual_machine" "linux" {
  count               = var.os_type == "linux" ? 1 : 0
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  size                = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  network_interface_ids = [azurerm_network_interface.nic.id]

  disable_password_authentication = var.ssh_pub_key != ""

  dynamic "admin_ssh_key" {
    for_each = var.ssh_pub_key != "" ? [1] : []
    content {
      username   = var.admin_username
      public_key = var.ssh_pub_key
    }
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  tags = {
    managed_by  = "overtime"
    environment = var.environment_prefix
    role        = var.role
  }
}

# ─── Windows VM ───────────────────────────────────────────────────────────────

resource "azurerm_windows_virtual_machine" "windows" {
  count               = var.os_type == "windows" ? 1 : 0
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  size                = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  network_interface_ids = [azurerm_network_interface.nic.id]
  vm_agent_platform_updates_enabled = true

  source_image_reference {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-smalldisk-g2"
    version   = "latest"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  tags = {
    managed_by  = "overtime"
    environment = var.environment_prefix
    role        = var.role
  }
}
