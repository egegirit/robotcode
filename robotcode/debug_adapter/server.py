from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from ..jsonrpc2.protocol import rpc_method
from ..jsonrpc2.server import JsonRPCServer, JsonRpcServerMode, TcpParams
from ..utils.logging import LoggingDescriptor
from .client import DAPClient, DAPClientError
from .protocol import DebugAdapterProtocol
from .types import (
    Capabilities,
    ConfigurationDoneArguments,
    ConfigurationDoneRequest,
    DisconnectArguments,
    DisconnectRequest,
    InitializeRequestArguments,
    LaunchRequestArguments,
    OutputEvent,
    OutputEventBody,
    RunInTerminalRequest,
    RunInTerminalRequestArguments,
    RunInTerminalResponseBody,
    SetBreakpointsArguments,
    SetBreakpointsRequest,
    SetBreakpointsResponseBody,
    TerminateArguments,
    TerminatedEvent,
    TerminateRequest,
    ThreadsResponseBody,
)


class OutputProtocol(asyncio.SubprocessProtocol):
    def __init__(self, parent: DAPServerProtocol) -> None:
        super().__init__()
        self.parent = parent

    def pipe_data_received(self, fd: Any, data: bytes) -> None:
        category = None

        if fd == 1:
            category = "stdout"
        elif fd == 2:
            category = "stderr"

        self.parent.send_event(OutputEvent(body=OutputEventBody(output=data.decode(), category=category)))


class DAPServerProtocol(DebugAdapterProtocol):
    _logger = LoggingDescriptor()

    def __init__(self) -> None:
        super().__init__()
        self._client: Optional[DAPClient] = None
        self._process: Optional[asyncio.subprocess.Process] = None

    @property
    def client(self) -> DAPClient:
        if self._client is None:
            raise DAPClientError("Client not defined.")

        return self._client

    @client.setter
    def client(self, value: DAPClient) -> None:
        self._client = value

    @rpc_method(name="initialize", param_type=InitializeRequestArguments)
    async def _initialize(self, arguments: InitializeRequestArguments) -> Capabilities:
        self._initialized = True

        return Capabilities(
            supports_configuration_done_request=True,
            # supports_function_breakpoints=True,
            # supports_conditional_breakpoints=True,
            # supports_hit_conditional_breakpoints=True,
            support_terminate_debuggee=True,
            support_suspend_debuggee=True,
            # supports_loaded_sources_request=True,
            supports_terminate_request=True,
            # supports_data_breakpoints=True
        )

    @rpc_method(name="launch", param_type=LaunchRequestArguments)
    async def _launch(
        self,
        request: str,
        python: str,
        cwd: str = ".",
        target: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, Optional[Any]]] = None,
        console: Optional[Literal["integrated", "external"]] = "integrated",
        name: Optional[str] = None,
        no_debug: Optional[bool] = None,
        pythonPath: Optional[List[str]] = None,  # noqa: N803
        launcherArgs: Optional[List[str]] = None,  # noqa: N803
        launcherTimeout: Optional[int] = None,  # noqa: N803
        variables: Optional[Dict[str, Any]] = None,
        arguments: Optional[LaunchRequestArguments] = None,
        **kwargs: Any,
    ) -> None:
        from ..utils.debugpy import find_free_port

        connect_timeout = launcherTimeout or 5

        port = find_free_port()

        launcher = Path(Path(__file__).parent, "launcher")

        run_args = [python, "-u", str(launcher)]

        run_args += ["-p", str(port)]
        run_args += ["--wait-for-client", "-t", str(connect_timeout)]
        run_args += ["--debugpy"]
        # run_args += ["--debugpy-wait-for-client"]

        run_args += launcherArgs or []
        run_args += ["--"]

        run_args += args or []

        if pythonPath:
            for e in pythonPath:
                run_args += ["-P", e]

        if variables:
            for k, v in variables.items():
                run_args += ["-v", f"{k}:{v}"]

        if target:
            run_args.append(target)

        env = {k: ("" if v is None else str(v)) for k, v in env.items()} if env else {}

        if console in ["integrated", "external"]:
            await self.send_request_async(
                RunInTerminalRequest(
                    arguments=RunInTerminalRequestArguments(
                        cwd=cwd,
                        args=run_args,
                        env=env,
                        kind=console if console in ["integrated", "external"] else None,
                        title=name,
                    )
                ),
                return_type=RunInTerminalResponseBody,
            )
        elif console in ["none"]:
            # self.process = await asyncio.create_subprocess_exec(
            #     run_args[0],
            #     *run_args[1:],
            #     cwd=cwd,
            #     env=env,
            #     stdout=asyncio.subprocess.PIPE,
            #     stderr=asyncio.subprocess.PIPE,
            #     stdin=asyncio.subprocess.PIPE,
            # )
            # await asyncio.get_event_loop().connect_read_pipe(
            #     lambda: OutputProtocol(self, "stdout"), self.process.stdout
            # )

            # await asyncio.get_event_loop().connect_read_pipe(
            #     lambda: OutputProtocol(self, "stderr"), self.process.stderr
            # )

            run_env: Dict[str, Optional[str]] = dict(os.environ)
            run_env.update(env)

            await asyncio.get_event_loop().subprocess_exec(
                lambda: OutputProtocol(self),
                *run_args,
                cwd=cwd,
                env=run_env,
            )

        else:
            raise Exception(f'Unknown console type "{console}".')

        self.client = DAPClient(self, TcpParams(None, port))
        try:
            await self.client.connect(connect_timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Can't connect to debug launcher.")

    @rpc_method(name="configurationDone", param_type=ConfigurationDoneArguments)
    async def _configuration_done(self, arguments: Optional[ConfigurationDoneArguments] = None) -> None:
        await self.client.protocol.send_request_async(ConfigurationDoneRequest(arguments=arguments))

    @rpc_method(name="disconnect", param_type=DisconnectArguments)
    async def _disconnect(self, arguments: Optional[DisconnectArguments] = None) -> None:
        if self._client is not None:
            if self.client.connected and not self.client.protocol.terminated:
                await self.client.protocol.send_request_async(DisconnectRequest(arguments=arguments))
        else:
            await self.send_event_async(TerminatedEvent())

    @rpc_method(name="setBreakpoints", param_type=SetBreakpointsArguments)
    async def _set_breakpoints(self, arguments: SetBreakpointsArguments) -> SetBreakpointsResponseBody:
        return await self.client.protocol.send_request_async(SetBreakpointsRequest(arguments=arguments))

    @rpc_method(name="threads")
    async def _threads(self) -> ThreadsResponseBody:
        # TODO
        return ThreadsResponseBody(threads=[])

    @_logger.call
    @rpc_method(name="terminate", param_type=TerminateArguments)
    async def _terminate(self, arguments: Optional[TerminateArguments] = None) -> None:
        if self.client.connected:
            return await self.client.protocol.send_request_async(TerminateRequest(arguments=arguments))
        else:
            await self.send_event_async(TerminatedEvent())


TCP_DEFAULT_PORT = 6611


class DebugAdapterServer(JsonRPCServer[DAPServerProtocol]):
    def __init__(
        self,
        mode: JsonRpcServerMode = JsonRpcServerMode.STDIO,
        tcp_params: TcpParams = TcpParams(None, TCP_DEFAULT_PORT),
    ):
        super().__init__(
            mode=mode,
            tcp_params=tcp_params,
        )

    def create_protocol(self) -> DAPServerProtocol:
        return DAPServerProtocol()