#!/usr/bin/env python3
"""Validate control contracts or emit P0 observations; never execute actions."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
import argparse
import json


class SafeArguments(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error echoes arbitrary user arguments and paths.
        raise ValueError('invalid_arguments')


def _dependency_unavailable() -> dict:
    return {'ok': False, 'code': 'dependency_unavailable', 'executable': False,
            'authority_verified': False,
            'install_hint': 'Install pinned dependencies in the selected Python environment: python -m pip install -r runtime/control-requirements.txt. No automatic installation is performed.'}


def main(argv=None) -> int:
    try:
        parser = SafeArguments(description=__doc__, epilog='Exit 0 includes valid denials and review requests. It is never execution permission.')
        commands = parser.add_subparsers(dest='command', required=True, parser_class=SafeArguments)
        validate = commands.add_parser('validate', help='Check shape and digest, not authority.')
        validate.add_argument('--input', required=True)
        observe = commands.add_parser('observe', help='Emit a non-executable declared-context observation.')
        observe.add_argument('--input', required=True)
        observe.add_argument('--context', required=True)
        observe.add_argument('--policy')
        args = parser.parse_args(argv)
    except ValueError:
        print(json.dumps({'ok': False, 'code': 'invalid_arguments', 'executable': False,
                          'authority_verified': False}))
        return 2
    try:
        if __package__:
            from . import control_contracts as contracts
            from .control_policy import evaluate_action
        else:
            import control_contracts as contracts
            from control_policy import evaluate_action
    except Exception:
        print(json.dumps(_dependency_unavailable()))
        return 2
    try:
        request = contracts.read_json(args.input)
        if args.command == 'validate':
            verified = contracts.validate_envelope(request)
            value = {'ok': True, 'record_type': 'contract_validation',
                     'schema_version': verified['schema_version'],
                     'validated_record_type': verified['envelope']['record_type'],
                     'digest': verified['envelope']['digest'],
                     'authenticity': 'not_verified', 'executable': False, 'authority_verified': False}
        else:
            context = contracts.read_json(args.context)
            policy = contracts.read_json(args.policy) if args.policy is not None else None
            value = evaluate_action(request, context, policy)
        print(json.dumps(value, sort_keys=True, separators=(',', ':')))
        if args.command == 'observe' and value['reason_codes'][0] in (
                'invalid_request', 'invalid_context', 'invalid_policy', 'unsupported_record_type'):
            return 2
        return 0
    except contracts.ControlContractError as error:
        # Safe fixed categories only; never print a library error, path or input.
        if error.code in ('dependency_missing', 'dependency_incompatible'):
            value = _dependency_unavailable()
        else:
            value = {'ok': False, 'code': 'invalid_input', 'executable': False, 'authority_verified': False}
    except OSError:
        value = {'ok': False, 'code': 'input_unavailable', 'executable': False, 'authority_verified': False}
    except Exception:
        value = {'ok': False, 'code': 'internal_error', 'executable': False, 'authority_verified': False}
    print(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
