provider "proxmox" {
  endpoint = var.pm_api_url
  username = var.pm_user
  insecure = var.pm_tls_insecure
  # Auth via environment variable (set by overtime CLI):
  #   Password auth:  PROXMOX_VE_PASSWORD
  #   API token auth: PROXMOX_VE_API_TOKEN
}