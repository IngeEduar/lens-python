from flask import Flask, render_template, jsonify, request
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.client import configuration
import subprocess

app = Flask(__name__)

config.load_kube_config()
configuration.assert_hostname = False
configuration.verify_ssl = False
v1 = client.CoreV1Api()

active_port_forwards = {}


@app.route('/')
def index():
    try:
        pods = v1.list_pod_for_all_namespaces(watch=False)
        pod_list = [{'name': pod.metadata.name, 'namespace': pod.metadata.namespace} for pod in pods.items]
        return render_template('index.html', pods=pod_list)
    except ApiException as e:
        return f"Error al listar pods: {e}", 500


@app.route('/pod-info', methods=['GET'])
def pod_info():
    pod_name = request.args.get('name')
    namespace = request.args.get('namespace')

    try:
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        pod_info = {
            'name': pod.metadata.name,
            'namespace': pod.metadata.namespace,
            'node': pod.spec.node_name,
            'status': pod.status.phase,
            'pod_ip': pod.status.pod_ip,
            'containers': [{'name': c.name, 'image': c.image} for c in pod.spec.containers]
        }
        return jsonify(pod_info)
    except ApiException as e:
        return jsonify({'error': str(e)}), 500


@app.route('/services')
def services():
    try:
        services = v1.list_service_for_all_namespaces(watch=False)
        service_list = [{'name': svc.metadata.name, 'namespace': svc.metadata.namespace} for svc in services.items]
        return render_template('services.html', services=service_list, active_port_forwards=active_port_forwards)
    except ApiException as e:
        return f"Error al listar servicios: {e}", 500


@app.route('/create-port-forward', methods=['POST'])
def create_port_forward():
    service_name = request.form.get('service_name')
    namespace = request.form.get('namespace')
    local_port = request.form.get('local_port')
    target_port = request.form.get('target_port')

    try:
        # Crear un comando de port-forward
        cmd = [
            'kubectl', 'port-forward',
            f'svc/{service_name}',
            f'{local_port}:{target_port}',
            '--namespace', namespace
        ]

        # Inicia el port-forward en un proceso separado
        process = subprocess.Popen(cmd)
        active_port_forwards[process.pid] = {
            'service_name': service_name,
            'namespace': namespace,
            'local_port': local_port,
            'target_port': target_port,
            'pid': process.pid
        }

        return jsonify({'success': True, 'pid': process.pid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/delete-port-forward', methods=['POST'])
def delete_port_forward():
    pid = int(request.form.get('pid'))

    try:
        if pid in active_port_forwards:
            subprocess.Popen(['kill', '-9', str(pid)])
            del active_port_forwards[pid]
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'No se encontró el proceso con ese PID'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
