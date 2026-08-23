// The browser and Python backend intentionally consume the same canonical file.
export const ADDRESS_CONTRACT_VERSION = "1.1.0";
export const ADDRESS_CONTRACT_PATH = "contracts/address-api.v1.schema.json";

export async function loadAddressContract(fetchImpl = fetch) {
  const response = await fetchImpl(`/${ADDRESS_CONTRACT_PATH}`);
  if (!response.ok) {
    throw new Error(`Unable to load address contract: HTTP ${response.status}`);
  }
  return response.json();
}
