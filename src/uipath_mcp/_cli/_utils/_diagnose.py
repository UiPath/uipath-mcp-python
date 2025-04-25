import os
import platform
import subprocess


def diagnose_binary(binary_path):
    """Diagnose why a binary file can't be executed."""
    results = {}

    # Check if file exists
    results["exists"] = os.path.exists(binary_path)
    if not results["exists"]:
        return f"Error: {binary_path} does not exist"

    # Get system architecture
    results["system_arch"] = platform.machine()
    results["system_os"] = platform.system()

    # Check file type using 'file' command
    try:
        file_output = subprocess.check_output(
            ["file", binary_path], universal_newlines=True
        )
        results["file_type"] = file_output.strip()
    except subprocess.CalledProcessError:
        results["file_type"] = "Could not determine file type (file command failed)"
    except FileNotFoundError:
        results["file_type"] = (
            "Could not determine file type (file command not available)"
        )

    # For Linux, check ELF header
    if platform.system() == "Linux":
        try:
            readelf_output = subprocess.check_output(
                ["readelf", "-h", binary_path], universal_newlines=True
            )
            # Extract architecture from readelf output
            arch_line = [
                line for line in readelf_output.splitlines() if "Machine:" in line
            ]
            if arch_line:
                results["binary_arch"] = arch_line[0].strip()
            else:
                results["binary_arch"] = "Could not determine binary architecture"
        except subprocess.CalledProcessError:
            results["binary_arch"] = "Not a valid ELF binary (readelf command failed)"
        except FileNotFoundError:
            results["binary_arch"] = (
                "Could not check ELF header (readelf command not available)"
            )

    # Print summary
    print(f"Diagnosis for {binary_path}:")
    print(f"File exists: {results['exists']}")
    print(f"System architecture: {results['system_arch']}")
    print(f"System OS: {results['system_os']}")
    print(f"File type: {results['file_type']}")
    if "binary_arch" in results:
        print(f"Binary architecture: {results['binary_arch']}")

    # Provide potential solution
    if "ELF" in results.get("file_type", "") and results["system_os"] == "Linux":
        if (
            "64-bit" in results["file_type"]
            and "x86-64" in results["file_type"]
            and results["system_arch"] != "x86_64"
        ):
            return (
                "Error: Binary was compiled for x86_64 architecture but your system is "
                + results["system_arch"]
            )
        elif (
            "ARM" in results.get("binary_arch", "")
            and "arm" not in results["system_arch"].lower()
        ):
            return (
                "Error: Binary was compiled for ARM architecture but your system is "
                + results["system_arch"]
            )

    return "Binary format may be incompatible with your system. You need a version compiled specifically for your architecture and operating system."
