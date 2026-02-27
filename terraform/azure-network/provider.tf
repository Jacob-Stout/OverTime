# Authentication is handled by the azurerm provider's credential chain:
#   1. Azure CLI  (az login)       — default for local use.
#   2. Service Principal           — ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID.
#   3. Managed Identity            — automatic on Azure compute.
#
# The Python orchestrator sets ARM_SUBSCRIPTION_ID before running terraform.

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
