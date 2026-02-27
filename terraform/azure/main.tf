# ─── VM Definitions ───────────────────────────────────────────────────────────
# Same logical topologies as Proxmox (ad-lab-xs, ad-lab-s, ad-lab-m, k8s-dev, jumphost).
# IPs are allocated as subnet_start + ip_offset within the subnet.
# vm_size defaults to var.default_vm_size (from the provisioning spec);
# add a per-VM "vm_size" key to override where needed.

locals {
  # Derive the first 3 octets and the 4th-octet start from the CIDR.
  # e.g. "192.168.0.64/26" → base "192.168.0", start 64
  subnet_base  = join(".", slice(split(".", split("/", var.subnet_cidr)[0]), 0, 3))
  subnet_start = tonumber(split(".", split("/", var.subnet_cidr)[0])[3])
  # Unique subnet name per scenario — avoids collisions when multiple scenarios share a VNet.
  subnet_name = "${var.environment_name_prefix}-${var.scenario}"

  vm_definitions = {
    "ad-lab-xs" = [
      { name_suffix = "ad-1a",     role = "ad",      os_type = "windows", ip_offset = 10, disk_gb = 30 },
      { name_suffix = "wutil-1a",  role = "wutil",   os_type = "windows", ip_offset = 11, disk_gb = 30 },
      { name_suffix = "gen-1a",    role = "general",  os_type = "windows", ip_offset = 12, disk_gb = 30 },
    ]

    "ad-lab-s" = [
      { name_suffix = "ad-1a",     role = "ad",      os_type = "windows", ip_offset = 10, disk_gb = 30 },
      { name_suffix = "wutil-1a",  role = "wutil",   os_type = "windows", ip_offset = 11, disk_gb = 30 },
      { name_suffix = "gen-1a",    role = "general",  os_type = "windows", ip_offset = 12, disk_gb = 30 },
      { name_suffix = "gen-1b",    role = "general",  os_type = "windows", ip_offset = 13, disk_gb = 30 },
    ]

    "ad-lab-m" = [
      { name_suffix = "ad-1a",     role = "ad",      os_type = "windows", ip_offset = 10, disk_gb = 30 },
      { name_suffix = "ad-2a",     role = "ad",      os_type = "windows", ip_offset = 11, disk_gb = 30 },
      { name_suffix = "wutil-1a",  role = "wutil",   os_type = "windows", ip_offset = 12, disk_gb = 30 },
      { name_suffix = "gen-1a",    role = "general",  os_type = "windows", ip_offset = 13, disk_gb = 30 },
      { name_suffix = "gen-1b",    role = "general",  os_type = "windows", ip_offset = 14, disk_gb = 30 },
    ]

    "k8s-dev" = [
      { name_suffix = "k8s-1a",    role = "ctrl",    os_type = "linux", ip_offset = 10, disk_gb = 30 },
      { name_suffix = "k8s-1b",    role = "ctrl",    os_type = "linux", ip_offset = 11, disk_gb = 30 },
      { name_suffix = "k8s-1c",    role = "ctrl",    os_type = "linux", ip_offset = 12, disk_gb = 30 },
      { name_suffix = "k8s-1d",    role = "work",    os_type = "linux", ip_offset = 13, disk_gb = 30 },
      { name_suffix = "k8s-1e",    role = "work",    os_type = "linux", ip_offset = 14, disk_gb = 30 },
    ]

    "jumphost" = [
      { name_suffix = "lutil-1a",  role = "lutil",   os_type = "linux", ip_offset = 10, disk_gb = 30 },
    ]
  }

  selected_vms = local.vm_definitions[var.scenario]
}

# ─── Network (per-scenario subnet within shared RG + VNet) ───────────────────

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
    for vm in local.selected_vms :
    vm.name_suffix => vm
  }

  name                = "${var.environment_name_prefix}-${each.value.name_suffix}"
  role                = each.value.role
  os_type             = each.value.os_type
  vm_size             = lookup(each.value, "vm_size", var.default_vm_size)
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
