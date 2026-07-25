"""
Pulse Orchestrator — Docker Sandbox Runner

Manages ephemeral Docker containers for safely testing repair patches.
Each repair attempt gets its own container that is destroyed afterwards.

Lifecycle:
  1. create_sandbox()  — Pull/build image, create container with project files
  2. apply_patch()     — Write and apply a unified diff inside the container
  3. run_tests()       — Execute the test command and capture output
  4. cleanup()         — Destroy the container and temporary files

Safety:
  - Containers have CPU and memory limits
  - Hard 60-second timeout on test execution
  - No network access from inside the container (--network=none)
  - Container is destroyed after every attempt
"""

import asyncio
import tempfile
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.utils.logger import setup_logger

logger = setup_logger("pulse.sandbox")

# Docker image name for the sandbox
SANDBOX_IMAGE = "pulse-sandbox:latest"
DOCKERFILE_PATH = Path(__file__).parent / "Dockerfile.sandbox"

# Resource limits
CONTAINER_TIMEOUT = 60  # seconds
CONTAINER_MEMORY = "512m"
CONTAINER_CPUS = "1.0"


@dataclass
class TestResult:
    """Result of running tests inside the sandbox."""
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class DockerRunner:
    """
    Manages Docker containers for the Repair Agent sandbox.

    Uses the Docker SDK for Python (docker-py) to create and manage
    ephemeral containers.
    """

    def __init__(self):
        self._client = None
        self._image_built = False

    def _get_client(self):
        """Lazy-init the Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
                # Verify Docker is running
                self._client.ping()
                logger.info("Docker client connected successfully")
            except ImportError:
                raise RuntimeError(
                    "Docker SDK not installed. Run: pip install docker"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Cannot connect to Docker. Is Docker Desktop running? Error: {e}"
                )
        return self._client

    async def ensure_image(self) -> None:
        """Build the sandbox Docker image if it doesn't exist."""
        if self._image_built:
            return

        client = self._get_client()

        # Check if image already exists
        try:
            client.images.get(SANDBOX_IMAGE)
            self._image_built = True
            logger.info(f"Sandbox image '{SANDBOX_IMAGE}' already exists")
            return
        except Exception:
            pass

        # Build the image
        logger.info(f"Building sandbox image from {DOCKERFILE_PATH}...")
        try:
            # Run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.images.build(
                    path=str(DOCKERFILE_PATH.parent),
                    dockerfile=DOCKERFILE_PATH.name,
                    tag=SANDBOX_IMAGE,
                    rm=True,
                )
            )
            self._image_built = True
            logger.info(f"Sandbox image '{SANDBOX_IMAGE}' built successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to build sandbox image: {e}")

    async def create_sandbox(self, project_path: Optional[str] = None) -> str:
        """
        Create an ephemeral Docker container for testing.

        Args:
            project_path: Optional path to the project directory to copy in.
                         If None, creates an empty workspace.

        Returns:
            Container ID
        """
        await self.ensure_image()
        client = self._get_client()

        logger.info("Creating sandbox container...")

        try:
            # Create container with resource limits and no network
            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None,
                lambda: client.containers.create(
                    image=SANDBOX_IMAGE,
                    command="sleep infinity",  # Keep alive for commands
                    detach=True,
                    mem_limit=CONTAINER_MEMORY,
                    nano_cpus=int(float(CONTAINER_CPUS) * 1e9),
                    network_mode="none",  # No network access
                    working_dir="/workspace",
                )
            )

            # Start the container
            await loop.run_in_executor(None, container.start)

            # Copy project files if provided
            if project_path and os.path.isdir(project_path):
                await self._copy_to_container(container, project_path)

            logger.info(f"Sandbox container created: {container.short_id}")
            container_id = container.id
            if container_id is None:
                raise RuntimeError("Sandbox container created but ID is missing")
            return str(container_id)

        except Exception as e:
            raise RuntimeError(f"Failed to create sandbox container: {e}")

    async def _copy_to_container(self, container, project_path: str) -> None:
        """Copy project files into the container's /workspace."""
        import tarfile
        import io

        logger.info(f"Copying project files from {project_path}...")

        # Create a tar archive of the project
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            for root, dirs, files in os.walk(project_path):
                # Skip common large directories
                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        'node_modules', '.git', '.venv', '__pycache__',
                        '.next', 'dist', 'build', '.pytest_cache',
                    }
                ]
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, project_path)
                    try:
                        tar.add(filepath, arcname=arcname)
                    except (PermissionError, OSError):
                        continue

        tar_stream.seek(0)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: container.put_archive("/workspace", tar_stream.getvalue())
        )

    async def apply_patch(self, container_id: str, patch: str) -> bool:
        """
        Apply a unified diff patch inside the container.

        Args:
            container_id: The container to apply the patch in
            patch: Unified diff patch text

        Returns:
            True if the patch was applied successfully
        """
        client = self._get_client()
        container = client.containers.get(container_id)

        logger.info(f"Applying patch in container {container.short_id}...")

        try:
            # Write the patch to a temp file inside the container
            loop = asyncio.get_event_loop()

            # First, write the patch content
            exec_result = await loop.run_in_executor(
                None,
                lambda: container.exec_run(
                    ["bash", "-c", f"cat > /tmp/fix.patch << 'PULSE_PATCH_EOF'\n{patch}\nPULSE_PATCH_EOF"],
                    workdir="/workspace",
                )
            )

            # Apply it with git apply (or patch)
            exec_result = await loop.run_in_executor(
                None,
                lambda: container.exec_run(
                    ["bash", "-c", "git apply /tmp/fix.patch 2>&1 || patch -p1 < /tmp/fix.patch 2>&1"],
                    workdir="/workspace",
                )
            )

            success = exec_result.exit_code == 0
            
            # The docker-py SDK types exec_result.output as a Union that includes Iterator.
            # With stream=False (default), it returns bytes.
            if isinstance(exec_result.output, bytes):
                output = exec_result.output.decode("utf-8", errors="replace")
            else:
                output = str(exec_result.output)

            if success:
                logger.info("Patch applied successfully")
            else:
                logger.warning(f"Patch apply failed: {output}")

            return success

        except Exception as e:
            logger.error(f"Failed to apply patch: {e}")
            return False

    async def run_tests(
        self,
        container_id: str,
        test_command: str = "pytest",
    ) -> TestResult:
        """
        Run the test suite inside the container.

        Args:
            container_id: The container to run tests in
            test_command: The test command to execute

        Returns:
            TestResult with pass/fail status and output
        """
        import time

        client = self._get_client()
        container = client.containers.get(container_id)

        logger.info(f"Running tests in container {container.short_id}: {test_command}")

        start_time = time.time()

        try:
            loop = asyncio.get_event_loop()

            # Run with timeout
            exec_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: container.exec_run(
                        ["bash", "-c", test_command],
                        workdir="/workspace",
                    )
                ),
                timeout=CONTAINER_TIMEOUT,
            )

            duration = time.time() - start_time
            
            if isinstance(exec_result.output, bytes):
                output = exec_result.output.decode("utf-8", errors="replace")
            else:
                output = str(exec_result.output)

            exit_code = exec_result.exit_code if exec_result.exit_code is not None else -1

            result = TestResult(
                passed=exit_code == 0,
                exit_code=exit_code,
                stdout=output,
                stderr="",  # exec_run combines stdout+stderr
                duration_seconds=round(duration, 2),
            )

            logger.info(
                f"Tests {'PASSED' if result.passed else 'FAILED'} "
                f"(exit code {result.exit_code}, {duration:.1f}s)"
            )

            return result

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            logger.error(f"Tests timed out after {CONTAINER_TIMEOUT}s")
            return TestResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=f"Tests timed out after {CONTAINER_TIMEOUT} seconds",
                duration_seconds=round(duration, 2),
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Failed to run tests: {e}")
            return TestResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=round(duration, 2),
            )

    async def cleanup(self, container_id: str) -> None:
        """Destroy a sandbox container."""
        try:
            client = self._get_client()
            container = client.containers.get(container_id)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: container.remove(force=True)
            )

            logger.info(f"Sandbox container {container_id[:12]} destroyed")
        except Exception as e:
            logger.warning(f"Failed to cleanup container {container_id[:12]}: {e}")

    async def is_available(self) -> bool:
        """Check if Docker is available and running."""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception:
            return False


# ─── Singleton ───
docker_runner = DockerRunner()
