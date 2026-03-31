/** Check if a file path is inside any of the disabled folders. */
export function isInDisabledFolder(filePath: string, disabledFolders: Set<string>): boolean {
  for (const folder of disabledFolders) {
    if (filePath === folder || filePath.startsWith(folder + "/")) {
      return true;
    }
  }
  return false;
}
