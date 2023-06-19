"""Tests for AWS Braket backends."""
import unittest
from typing import Dict, List
from unittest import TestCase
from unittest.mock import Mock

from botocore import errorfactory
from qiskit import QuantumCircuit, transpile, BasicAer
from qiskit.algorithms import VQE, VQEResult
from qiskit.algorithms.optimizers import (
    SLSQP,
)
from qiskit.circuit.library import TwoLocal
from qiskit.circuit.random import random_circuit
from qiskit.opflow import (
    I,
    X,
    Z,
)
from qiskit.result import Result
from qiskit.transpiler import Target
from qiskit.utils import QuantumInstance

from qiskit_braket_provider import AWSBraketProvider, version
from qiskit_braket_provider.providers import AWSBraketBackend, BraketLocalBackend
from qiskit_braket_provider.providers.adapter import aws_device_to_target
from tests.providers.mocks import RIGETTI_MOCK_GATE_MODEL_QPU_CAPABILITIES


def combine_dicts(
    dict1: Dict[str, float], dict2: Dict[str, float]
) -> Dict[str, List[float]]:
    """Combines dictionaries with different keys.

    Args:
        dict1: first
        dict2: second

    Returns:
        merged dicts with list of keys
    """
    combined_dict: Dict[str, List[float]] = {}
    for key in dict1.keys():
        if key in combined_dict:
            combined_dict[key].append(dict1[key])
        else:
            combined_dict[key] = [dict1[key]]
    for key in dict2.keys():
        if key in combined_dict:
            combined_dict[key].append(dict2[key])
        else:
            combined_dict[key] = [dict2[key]]
    return combined_dict


class TestAWSBraketBackend(TestCase):
    """Tests BraketBackend."""

    def test_device_backend(self):
        """Tests device backend."""
        device = Mock()
        device.properties = RIGETTI_MOCK_GATE_MODEL_QPU_CAPABILITIES
        backend = AWSBraketBackend(device)
        self.assertTrue(backend)
        self.assertIsInstance(backend.target, Target)
        self.assertIsNone(backend.max_circuits)
        user_agent = f"QiskitBraketProvider/" f"{version.__version__}"
        device.aws_session.add_braket_user_agent.assert_called_with(user_agent)
        with self.assertRaises(NotImplementedError):
            backend.drive_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.acquire_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.measure_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.control_channel([0, 1])

    def test_local_backend(self):
        """Tests local backend."""
        backend = BraketLocalBackend(name="default")
        self.assertTrue(backend)
        self.assertIsInstance(backend.target, Target)
        self.assertIsNone(backend.max_circuits)
        with self.assertRaises(NotImplementedError):
            backend.drive_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.acquire_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.measure_channel(0)
        with self.assertRaises(NotImplementedError):
            backend.control_channel([0, 1])

    def test_local_backend_output(self):
        """Test local backend output"""
        first_backend = BraketLocalBackend(name="braket_dm")
        self.assertEqual(first_backend.backend_name, "braket_dm")

    def test_local_backend_circuit(self):
        """Tests local backend with circuit."""
        backend = BraketLocalBackend(name="default")
        circuits = []

        # Circuit 0
        q_c = QuantumCircuit(2)
        q_c.x(0)
        q_c.cx(0, 1)
        circuits.append(q_c)

        # Circuit 1
        q_c = QuantumCircuit(2)
        q_c.h(0)
        q_c.cx(0, 1)
        circuits.append(q_c)

        results = []
        for circuit in circuits:
            results.append(backend.run(circuit).result())

        # Result 0
        self.assertEqual(results[0].get_counts(), {"11": 1024})
        # Result 1
        _00 = results[1].get_counts()["00"]
        _11 = results[1].get_counts()["11"]
        self.assertEqual(_00 + _11, 1024)

    def test_local_backend_circuit_shots0(self):
        """Tests local backend with circuit with shots=0."""
        backend = BraketLocalBackend(name="default")

        circuit = QuantumCircuit(2)
        circuit.x(0)
        circuit.cx(0, 1)

        result = backend.run(circuit, shots=0).result()

        statevector = result.get_statevector()
        self.assertEqual(statevector[0], 0.0 + 0.0j)
        self.assertEqual(statevector[1], 0.0 + 0.0j)
        self.assertEqual(statevector[2], 0.0 + 0.0j)
        self.assertEqual(statevector[3], 1.0 + 0.0j)

    def test_vqe(self):
        """Tests VQE."""
        local_simulator = BraketLocalBackend(name="default")

        h2_op = (
            (-1.052373245772859 * I ^ I)
            + (0.39793742484318045 * I ^ Z)
            + (-0.39793742484318045 * Z ^ I)
            + (-0.01128010425623538 * Z ^ Z)
            + (0.18093119978423156 * X ^ X)
        )

        quantum_instance = QuantumInstance(
            local_simulator, seed_transpiler=42, seed_simulator=42
        )
        ansatz = TwoLocal(rotation_blocks="ry", entanglement_blocks="cz")
        slsqp = SLSQP(maxiter=1)

        vqe = VQE(ansatz, optimizer=slsqp, quantum_instance=quantum_instance)

        result = vqe.compute_minimum_eigenvalue(h2_op)

        self.assertIsInstance(result, VQEResult)
        self.assertEqual(len(result.optimal_parameters), 8)
        self.assertEqual(len(list(result.optimal_point)), 8)

    def test_random_circuits(self):
        """Tests with random circuits."""
        backend = BraketLocalBackend(name="braket_sv")
        aer_backend = BasicAer.get_backend("statevector_simulator")

        for i in range(1, 10):
            with self.subTest(f"Random circuit with {i} qubits."):
                circuit = random_circuit(i, 5, seed=42)
                braket_result = backend.run(circuit, shots=1000).result().get_counts()

                transpiled_aer_circuit = transpile(
                    circuit, backend=aer_backend, seed_transpiler=42
                )
                aer_result = (
                    aer_backend.run(transpiled_aer_circuit, shots=1000)
                    .result()
                    .get_counts()
                )

                combined_results = combine_dicts(
                    {k: float(v) / 1000.0 for k, v in braket_result.items()}, aer_result
                )

                for key, values in combined_results.items():
                    if len(values) == 1:
                        self.assertTrue(
                            values[0] < 0.05,
                            f"Missing {key} key in one of the results.",
                        )
                    else:
                        percent_diff = abs(
                            ((float(values[0]) - values[1]) / values[0]) * 100
                        )
                        abs_diff = abs(values[0] - values[1])
                        self.assertTrue(
                            percent_diff < 10 or abs_diff < 0.05,
                            f"Key {key} with percent difference {percent_diff} "
                            f"and absolute difference {abs_diff}. Original values {values}",
                        )

    @unittest.skip("Call to external resources.")
    def test_retrieve_job(self):
        """Tests retrieve task by id."""
        backend = AWSBraketProvider().get_backend("SV1")
        circuits = [
            transpile(
                random_circuit(3, 2, seed=seed), backend=backend, seed_transpiler=42
            )
            for seed in range(3)
        ]
        job = backend.run(circuits, shots=10)
        task_id = job.task_id()
        retrieved_job = backend.retrieve_job(task_id)

        job_result: Result = job.result()
        retrieved_job_result: Result = retrieved_job.result()

        self.assertEqual(job_result.task_id, retrieved_job_result.task_id)
        self.assertEqual(job_result.status, retrieved_job_result.status)
        self.assertEqual(
            job_result.backend_version, retrieved_job_result.backend_version
        )
        self.assertEqual(job_result.backend_name, retrieved_job_result.backend_name)

    @unittest.skip("Call to external resources.")
    def test_running_incompatible_verbatim_circuit_on_aspen_raises_error(self):
        """Tests working of verbatim=True and disable_qubit_rewiring=True.

        Note that in case of Rigetti devices, both of those parameters are
        needed if one wishes to run instructions wrapped in verbatim boxes.
        """
        device = AWSBraketProvider().get_backend("Aspen-M-2")
        circuit = QuantumCircuit(2)
        circuit.cnot(0, 1)

        with self.assertRaises(errorfactory.ClientError):
            device.run(circuit, verbatim=True, disable_qubit_rewiring=True)

    @unittest.skip("Call to external resources.")
    def test_running_circuit_with_disabled_rewiring_requires_matching_topolog(self):
        """Tests working of disable_qubit_rewiring=True."""
        device = AWSBraketProvider().get_backend("Aspen-M-2")
        circuit = QuantumCircuit(4)
        circuit.cz(0, 3)

        with self.assertRaises(errorfactory.ClientError):
            device.run(circuit, disable_qubit_rewiring=True)

    @unittest.skip("Call to external resources.")
    def test_native_circuits_with_measurements_can_be_run_in_verbatim_mode(self):
        """Tests running circuit with measurement in verbatim mode."""
        backend = AWSBraketProvider().get_backend("Aspen-M-2")
        circuit = QuantumCircuit(2)
        circuit.cz(0, 1)
        circuit.measure_all()

        result = backend.run(
            circuit, shots=10, verbatim=True, disable_qubit_rewiring=True
        ).result()

        self.assertEqual(sum(result.get_counts().values()), 10)


class TestAWSBackendTarget(TestCase):
    """Tests target for AWS Braket backend."""

    def test_target(self):
        """Tests target."""
        mock_device = Mock()
        mock_device.properties = RIGETTI_MOCK_GATE_MODEL_QPU_CAPABILITIES

        target = aws_device_to_target(mock_device)
        self.assertEqual(target.num_qubits, 30)
        self.assertEqual(len(target.operations), 2)
        self.assertEqual(len(target.instructions), 60)
        self.assertIn("Target for AWS Device", target.description)
