import debug from "debug";
import { readFile } from "fs/promises";
import { globby } from "globby";
import path from "path";
import { simpleGit } from "simple-git";
import { parse as yamlParse } from "yaml";
import { RuleResult } from "../rule-result.js";
import { Rule } from "../rule.js";
import { fileExists, normalizePath, readTspConfig } from "../utils.js";

// Enable simple-git debug logging to improve console output
debug.enable("simple-git");

export class FolderStructureRule implements Rule {
  readonly name = "FolderStructure";
  readonly description = "Verify spec directory's folder structure and naming conventions.";

  /**
   * Determines if v2 folder structure compliance should be enforced.
   * 
   * This method checks if the target branch (usually main) already has v2-compliant folder structures.
   * If the target branch is already using v2 structure, then all new changes must also comply with v2.
   * 
   * When v2 compliance is enforced, new specifications must use the v2 folder structure:
   * - Data-plane: specification/service/data-plane/ServiceName
   * - Resource-manager: specification/service/resource-manager/Microsoft.ServiceName/ServiceName
   * 
   * @param folder The folder being validated
   * @param folderStruct The folder structure array (path segments)
   * @returns Promise<boolean> True if v2 compliance should be enforced
   */
  private async shouldEnforceV2Compliance(gitRoot: string, folder: string): Promise<boolean> {
    try {
      const git = simpleGit(gitRoot);
      
      // Get current branch info to find target branch (usually main)
      const branchInfo = await git.branch();
      const currentBranch = branchInfo.current;
      
      // Don't enforce if we're already on main/target branch
      if (currentBranch === "main") {
        return false;
      }
      
      // Get service directory relative to specification folder
      const folderStruct = folder.split(path.sep);
      const specIndex = folderStruct.indexOf("specification");
      if (specIndex === -1 || specIndex + 1 >= folderStruct.length) {
        return false;
      }
      
      const serviceDir = `specification/${folderStruct[specIndex + 1]}`;
      
      // Check if target branch uses v2 structure by listing directories
      const targetBranch = "main"; // Could be made configurable
      const output = await git.raw(["ls-tree", "-d", "--name-only", `${targetBranch}:${serviceDir}`]);
      
      const directories = output.trim().split("\n").filter(dir => dir.trim());
      const hasV2Structure = directories.some(dir => 
        dir.trim() === "data-plane" || dir.trim() === "resource-manager"
      );
      
      return hasV2Structure;
    } catch (error) {
      // If git operations fail, don't enforce v2 compliance
      return false;
    }
  }

  /**
   * Validates that a folder structure complies with v2 guidelines.
   * 
   * This method enforces strict v2 folder structure rules:
   * - Folders must use either data-plane or resource-manager structure
   * - Data-plane folders must be exactly one level under 'data-plane'
   * - Resource-manager folders must be exactly two levels under 'resource-manager'
   * - Service names must use PascalCase with alphanumeric characters only
   * - RP namespace must match the regex /^[A-Za-z0-9\.]+$/
   * 
   * @param folderStruct The folder structure array (path segments)
   * @returns Promise<{success: boolean, errorOutput: string}> Validation result
   */
  private async validateV2Compliance(folderStruct: string[]): Promise<{success: boolean, errorOutput: string}> {
    let success = true;
    let errorOutput = "";
    
    // Check if this folder violates v2 structure guidelines
    const hasDataPlane = folderStruct.includes("data-plane");
    const hasResourceManager = folderStruct.includes("resource-manager");
    
    if (!hasDataPlane && !hasResourceManager) {
      // This is a v1 structure folder - should be migrated to v2
      success = false;
      errorOutput += `Invalid folder structure: The target branch is already using folder structure v2. ` +
        `New specifications must use v2 structure with either 'data-plane' or 'resource-manager' in the path. ` +
        `Please use a path like 'specification/${folderStruct[1]}/data-plane/ServiceName' or ` +
        `'specification/${folderStruct[1]}/resource-manager/Microsoft.ServiceName/ServiceName'.\n`;
    } else {
      // This is a v2 structure folder - ensure it follows v2 guidelines correctly
      if (hasDataPlane && hasResourceManager) {
        success = false;
        errorOutput += `Invalid folder structure: Path cannot contain both 'data-plane' and 'resource-manager'.\n`;
      } else if (hasDataPlane) {
        // Validate data-plane structure: specification/{orgName}/data-plane/{serviceName}/
        const dataPlaneIndex = folderStruct.indexOf("data-plane");
        if (folderStruct.length !== dataPlaneIndex + 2) {
          success = false;
          errorOutput += `Invalid folder structure: TypeSpec for data-plane specs must be exactly 4 levels deep. ` +
            `Required structure: 'specification/{orgName}/data-plane/{serviceName}/'. ` +
            `Current path has ${folderStruct.length} levels: '${folderStruct.join("/")}'.\n`;
        } else {
          // Validate orgName (must be lowercase)
          const orgName = folderStruct[dataPlaneIndex - 1];
          if (orgName !== orgName.toLowerCase()) {
            success = false;
            errorOutput += `Invalid folder structure: orgName '${orgName}' must be all lowercase.\n`;
          }
          
          // Validate serviceName (PascalCase, no special characters)
          const serviceFolder = folderStruct[folderStruct.length - 1];
          const serviceRegex = /^[A-Z][A-Za-z0-9]*$/;
          if (!serviceRegex.test(serviceFolder)) {
            success = false;
            errorOutput += `Invalid folder structure: Service folder '${serviceFolder}' must be PascalCase without any special characters (e.g. dot, hyphen, underscore).\n`;
          }
        }
      } else if (hasResourceManager) {
        // Validate resource-manager structure: specification/{orgName}/resource-manager/{rpNamespace}/{serviceName}/
        const resourceManagerIndex = folderStruct.indexOf("resource-manager");
        if (folderStruct.length !== resourceManagerIndex + 3) {
          success = false;
          errorOutput += `Invalid folder structure: TypeSpec for resource-manager specs must be exactly 5 levels deep. ` +
            `Required structure: 'specification/{orgName}/resource-manager/{rpNamespace}/{serviceName}/'. ` +
            `Current path has ${folderStruct.length} levels: '${folderStruct.join("/")}'.\n`;
        } else {
          // Validate orgName (must be lowercase)
          const orgName = folderStruct[resourceManagerIndex - 1];
          if (orgName !== orgName.toLowerCase()) {
            success = false;
            errorOutput += `Invalid folder structure: orgName '${orgName}' must be all lowercase.\n`;
          }
          
          const rpNamespaceFolder = folderStruct[folderStruct.length - 2];
          const serviceFolder = folderStruct[folderStruct.length - 1];
          
          // Validate rpNamespace (must be A.B format with PascalCase)
          const rpNamespaceRegex = /^[A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*$/;
          if (!rpNamespaceRegex.test(rpNamespaceFolder)) {
            success = false;
            errorOutput += `Invalid folder structure: RPNamespace folder '${rpNamespaceFolder}' must be in format 'A.B' where A and B are PascalCase (e.g. 'Microsoft.ServiceName').\n`;
          }
          
          // Validate serviceName (PascalCase, no special characters)
          const serviceRegex = /^[A-Z][A-Za-z0-9]*$/;
          if (!serviceRegex.test(serviceFolder)) {
            success = false;
            errorOutput += `Invalid folder structure: Service folder '${serviceFolder}' must be PascalCase without any special characters (e.g. dot, hyphen, underscore).\n`;
          }
        }
      }
    }
    
    return { success, errorOutput };
  }

  async execute(folder: string): Promise<RuleResult> {
    let success = true;
    let stdOutput = "";
    let errorOutput = "";
    const gitRoot = normalizePath(await simpleGit(folder).revparse("--show-toplevel"));
    const relativePath = path.relative(gitRoot, folder).split(path.sep).join("/");

    // If the folder containing TypeSpec sources is under "data-plane" or "resource-manager", the spec
    // must be using "folder structure v2".  Otherwise, it must be using v1.
    const hasDataPlane = relativePath.includes("data-plane");
    const hasResourceManager = relativePath.includes("resource-manager");
    const pathSegments = relativePath.split("/");
    
    // General depth validation - applies to ALL folder structures
    if (pathSegments.length > 5) {
      return {
        success: false,
        stdOutput: stdOutput,
        errorOutput: `Please limit TypeSpec folder depth to 5 levels or less (specification/org/type/namespace/service). Current path has ${pathSegments.length} levels.\n`,
      };
    }
    
    let structureVersion = 1; // default to v1
    
    if (hasDataPlane || hasResourceManager) {
      if (hasDataPlane) {
        // Check if data-plane is in position 2 (specification/orgname/data-plane/...)
        const dataPlaneIndex = pathSegments.indexOf("data-plane");
        if (dataPlaneIndex >= 2) {
          structureVersion = 2;
        }
      } else if (hasResourceManager) {
        // Check if resource-manager is in position 2 (specification/orgname/resource-manager/...)
        const resourceManagerIndex = pathSegments.indexOf("resource-manager");
        if (resourceManagerIndex >= 2) {
          structureVersion = 2;
        }
      }
      // If it has data-plane/resource-manager but in wrong position, it's still v1 (malformed)
    }

    stdOutput += `folder: ${folder}\n`;
    if (!(await fileExists(folder))) {
      return {
        success: false,
        stdOutput: stdOutput,
        errorOutput: `Folder '${folder}' does not exist.\n`,
      };
    }

    const tspConfigs = await globby([`${folder}/**tspconfig.*`]);
    stdOutput += `config files: ${JSON.stringify(tspConfigs)}\n`;
    tspConfigs.forEach((file: string) => {
      if (!file.endsWith("tspconfig.yaml")) {
        success = false;
        errorOutput += `Invalid config file '${file}'.  Must be named 'tspconfig.yaml'.\n`;
      }
    });

    // Verify tspconfig, main.tsp, examples/
    const mainExists = await fileExists(path.join(folder, "main.tsp"));
    const clientExists = await fileExists(path.join(folder, "client.tsp"));
    const tspConfigExists = await fileExists(path.join(folder, "tspconfig.yaml"));

    if (!mainExists && !clientExists) {
      errorOutput += `Invalid folder structure: Spec folder must contain main.tsp or client.tsp.`;
      success = false;
    }

    if (mainExists && !(await fileExists(path.join(folder, "examples")))) {
      errorOutput += `Invalid folder structure: Spec folder with main.tsp must contain examples folder.`;
      success = false;
    }

    const folderStruct = relativePath.split("/").filter(Boolean);

    // Verify top level folder is lower case and remove empty entries when splitting by slash
    if (folderStruct[1].match(/[A-Z]/g)) {
      success = false;
      errorOutput += `Invalid folder name. Folders under specification/ must be lower case.\n`;
    }

    // Check if target branch is using v2 structure and apply stricter validation
    const shouldEnforceV2 = await this.shouldEnforceV2Compliance(gitRoot, folder);
    if (shouldEnforceV2) {
      const v2Validation = await this.validateV2Compliance(folderStruct);
      if (!v2Validation.success) {
        success = false;
        errorOutput += v2Validation.errorOutput;
      }
    }

    if (structureVersion === 1) {
      const packageFolder = folderStruct[folderStruct.length - 1];

      if (!packageFolder.includes("Shared") && !tspConfigExists) {
        errorOutput += `Invalid folder structure: Spec folder must contain tspconfig.yaml.`;
        success = false;
      }

      // Verify package folder is at most 3 levels deep (for v1 specifically)
      if (folderStruct.length > 4) {
        success = false;
        errorOutput += `Please limit TypeSpec folder depth to 3 levels or less for v1 structure (specification/service/package)`;
      }

      // Verify second level folder is capitalized after each '.'
      if (/(^|\. *)([a-z])/g.test(packageFolder)) {
        success = false;
        errorOutput += `Invalid folder name. Folders under specification/${folderStruct[1]} must be capitalized after each '.'\n`;
      }

      // Verify 'Shared' follows 'Management'
      if (packageFolder.includes("Management") && packageFolder.includes("Shared")) {
        if (!packageFolder.includes("Management.Shared")) {
          success = false;
          errorOutput += `Invalid folder name. For management libraries with a shared component, 'Shared' should follow 'Management'.`;
        }
      }

      if (tspConfigExists) {
        const configText = await readTspConfig(folder);
        const config = yamlParse(configText);
        const rpFolder =
          config?.options?.["@azure-tools/typespec-autorest"]?.["azure-resource-provider-folder"];
        stdOutput += `azure-resource-provider-folder: ${JSON.stringify(rpFolder)}\n`;

        if (
          rpFolder?.trim()?.endsWith("resource-manager") &&
          !packageFolder.endsWith(".Management")
        ) {
          errorOutput += `Invalid folder structure: TypeSpec for resource-manager specs must be in a folder ending with '.Management'`;
          success = false;
        } else if (
          !rpFolder?.trim()?.endsWith("resource-manager") &&
          packageFolder.endsWith(".Management")
        ) {
          errorOutput += `Invalid folder structure: TypeSpec for data-plane specs or shared code must be in a folder NOT ending with '.Management'`;
          success = false;
        }
      }
    } else if (structureVersion === 2) {
      if (!tspConfigExists) {
        errorOutput += `Invalid folder structure: Spec folder must contain tspconfig.yaml.`;
        success = false;
      }

      const specType = folder.includes("data-plane") ? "data-plane" : "resource-manager";
      if (specType === "data-plane") {
        if (folderStruct.length !== 4) {
          errorOutput +=
            "Invalid folder structure: TypeSpec for data-plane specs must be exactly 4 levels deep. Required structure: 'specification/{orgName}/data-plane/{serviceName}/'.";
          success = false;
        } else {
          // Validate orgName (must be lowercase)
          const orgName = folderStruct[1];
          if (orgName !== orgName.toLowerCase()) {
            success = false;
            errorOutput += `Invalid folder structure: orgName '${orgName}' must be all lowercase.`;
          }
        }
      } else if (specType === "resource-manager") {
        if (folderStruct.length !== 5) {
          errorOutput +=
            "Invalid folder structure: TypeSpec for resource-manager specs must be exactly 5 levels deep. Required structure: 'specification/{orgName}/resource-manager/{rpNamespace}/{serviceName}/'.";
          success = false;
        } else {
          // Validate orgName (must be lowercase)
          const orgName = folderStruct[1];
          if (orgName !== orgName.toLowerCase()) {
            success = false;
            errorOutput += `Invalid folder structure: orgName '${orgName}' must be all lowercase.`;
          }

          const rpNamespaceFolder = folderStruct[folderStruct.length - 2];
          
          // Validate rpNamespace (must be A.B format with PascalCase)
          const rpNamespaceRegex = /^[A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*$/;
          if (!rpNamespaceRegex.test(rpNamespaceFolder)) {
            success = false;
            errorOutput += `Invalid folder structure: RPNamespace folder '${rpNamespaceFolder}' must be in format 'A.B' where A and B are PascalCase (e.g. 'Microsoft.ServiceName').`;
          }
        }
      }

      // Validate serviceName (PascalCase, no special characters)
      const serviceRegex = /^[A-Z][A-Za-z0-9]*$/;
      const serviceFolder = folderStruct[folderStruct.length - 1];

      if (!serviceRegex.test(serviceFolder)) {
        success = false;
        errorOutput += `Invalid folder structure: Service folder '${serviceFolder}' must be PascalCase without any special characters (e.g. dot, hyphen, underscore).`;
      }
    }

    // Ensure specs only import files from same folder under "specification"
    stdOutput += "imports:\n";

    const allowedImportRoot =
      structureVersion === 1 ? path.join(...folderStruct.slice(0, 2)) : folder;
    stdOutput += `  ${allowedImportRoot}\n`;

    const allowedImportRootResolved = path.resolve(gitRoot, allowedImportRoot);

    const tsps = await globby("**/*.tsp", { cwd: allowedImportRootResolved });

    for (const tsp of tsps) {
      const tspResolved = path.resolve(allowedImportRootResolved, tsp);

      const pattern = /^\s*import\s+['"]([^'"]+)['"]\s*;\s*$/gm;
      const text = await readFile(tspResolved, { encoding: "utf8" });
      const imports = [...text.matchAll(pattern)].map((m) => m[1]);

      // The path specified in the import must either start with "./" or "../", or be an absolute path.
      // The path should either point to a directory, or have an extension of either ".tsp" or ".js".
      // https://typespec.io/docs/language-basics/imports/
      //
      // We don't bother checking if the path has an extension of ".tsp" or ".js", because a directory
      // is also valid, and a directory could be named anything.  We only care if the path is under
      // $teamFolder, so we just treat anything that looks like a relative or absolute path,
      // as a path.
      const fileImports = imports.filter(
        (i) => i.startsWith("./") || i.startsWith("../") || path.isAbsolute(i),
      );

      stdOutput += `    ${tsp}: ${JSON.stringify(fileImports)}\n`;

      for (const fileImport of fileImports) {
        const fileImportResolved = path.resolve(path.dirname(tspResolved), fileImport);

        const relative = path.relative(allowedImportRootResolved, fileImportResolved);

        if (relative.startsWith("..")) {
          errorOutput +=
            `Invalid folder structure: '${tsp}' imports '${fileImport}', ` +
            `which is outside '${path.relative(gitRoot, allowedImportRoot)}'`;
          success = false;
        }
      }
    }

    return {
      success: success,
      stdOutput: stdOutput,
      errorOutput: errorOutput,
    };
  }
}
