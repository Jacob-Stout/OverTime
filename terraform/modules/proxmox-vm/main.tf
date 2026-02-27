resource "proxmox_virtual_environment_vm" "this" {
  name        = var.name
  description = "Role: ${var.role} | OS: ${var.os_type}"

  node_name = var.node_name
  vm_id     = var.vm_id

  clone {
    vm_id = var.template_id
    full  = false
  }

  agent {
    enabled = true
    timeout = "10m"
  }

  cpu {
    cores = var.cpu
  }

  memory {
    dedicated = var.memory
  }

  disk {
    datastore_id = var.storage_pool
    interface    = "scsi0"
    size         = var.disk_size
    iothread     = true
  }

  network_device {
    bridge   = var.network_bridge
    firewall = false
  }

  # Empty CD-ROM — kernel needs this to detect cloud-init ISO
  cdrom {
    file_id = "none"
  }

  initialization {
    datastore_id = var.storage_pool

    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.vm_gateway
      }
    }

    dns {
      servers = var.dns_servers
    }

    # Cloud-init creates this user on Linux VMs.  Ansible then connects
    # as the same user.  On Windows (Cloudbase-init), the username field
    # is ignored — the template's built-in administrator is used instead.
    user_account {
      username = var.ansible_user
      keys     = [var.ssh_pub_key]
      password = var.ci_password
    }
  }

  bios          = var.bios
  scsi_hardware = "virtio-scsi-single"
  tags          = [var.role]

  # Lifecycle rules — ignore settings inherited from golden image template
  lifecycle {
    ignore_changes = [
      vga,
      disk[0].ssd,
    ]
  }
}
