/*
This is a Terraform configuration file that creates Proxmox VMs using the BPG provider (bpg/proxmox).
The VM list is passed in via var.vm_list from the provisioning spec. Each VM object specifies
name_suffix, role, cpu, disk_size, os_type, and ip_offset. The configuration creates a
Proxmox VM for each entry in the list using the proxmox_virtual_environment_vm resource.
*/

locals {
  # Derive the first 3 octets and the 4th-octet start from the CIDR.
  # e.g. "192.168.0.0/24" → base "192.168.0", start 0
  subnet_base  = join(".", slice(split(".", split("/", var.subnet_cidr)[0]), 0, 3))
  subnet_start = tonumber(split(".", split("/", var.subnet_cidr)[0])[3])
}

module "vm" {
  source   = "../modules/proxmox-vm"
  for_each = {
    for vm in var.vm_list :
    vm.name_suffix => vm
  }

  name              = "${var.environment_name_prefix}-${each.value.name_suffix}"
  role              = each.value.role
  cpu               = each.value.cpu
  memory            = each.value.memory != null ? each.value.memory : var.default_memory
  disk_size         = tonumber(replace(each.value.disk_size, "G", ""))
  os_type           = each.value.os_type
  template_id       = each.value.os_type == "windows" ? var.windows_template_id : var.linux_template_id
  ip_address        = "${local.subnet_base}.${local.subnet_start + each.value.ip_offset}/${split("/", var.subnet_cidr)[1]}"
  vm_gateway        = var.vm_gateway
  network_bridge    = var.network_bridge
  node_name         = var.node_name
  storage_pool      = var.storage_pool
  vm_id             = var.vm_id_start + index(keys({ for vm in var.vm_list : vm.name_suffix => vm }), each.key)
  bios              = "ovmf"
  ansible_user      = var.ansible_user
  ssh_pub_key       = var.ssh_pub_key
  ci_password       = var.ci_password
  dns_servers       = var.dns_servers
}
