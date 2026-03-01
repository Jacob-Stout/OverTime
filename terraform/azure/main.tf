# ─── VM Definitions ───────────────────────────────────────────────────────────
# The VM list is passed in via var.vm_list from the provisioning spec.
# IPs are allocated as subnet_start + ip_offset within the subnet.
# vm_size defaults to var.default_vm_size; add a per-VM "vm_size" key to override.

locals {
  # Derive the first 3 octets and the 4th-octet start from the CIDR.
  # e.g. "192.168.0.64/26" → base "192.168.0", start 64
  subnet_base  = join(".", slice(split(".", split("/", var.subnet_cidr)[0]), 0, 3))
  subnet_start = tonumber(split(".", split("/", var.subnet_cidr)[0])[3])
  subnet_name  = var.workspace
}

# ─── Network (per-environment subnet within shared RG + VNet) ────────────────

module "network" {
  source = "../modules/azure-network"

  resource_group_name   = var.resource_group_name
  vnet_name             = var.vnet_name
  vnet_cidr             = var.vnet_cidr
  subnet_name           = local.subnet_name
  subnet_cidr           = var.subnet_cidr
  environment_prefix    = var.environment_name_prefix
  allowed_source_prefix = var.allowed_source_prefix
}

# ─── VMs ──────────────────────────────────────────────────────────────────────

module "vm" {
  source   = "../modules/azure-vm"
  for_each = {
    for vm in var.vm_list :
    vm.name_suffix => vm
  }

  name                = "${var.environment_name_prefix}-${each.value.name_suffix}"
  role                = each.value.role
  os_type             = each.value.os_type
  vm_size             = var.default_vm_size
  resource_group_name = module.network.resource_group_name
  location            = module.network.resource_group_location
  subnet_id           = module.network.subnet_id
  private_ip_address  = "${local.subnet_base}.${local.subnet_start + each.value.ip_offset}"
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  ssh_pub_key         = var.ssh_pub_key
  os_disk_size_gb     = each.value.disk_gb
  environment_prefix  = var.environment_name_prefix
  assign_public_ip    = contains(["lutil", "wutil"], each.value.role)
}
