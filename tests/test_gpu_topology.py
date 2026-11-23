from gputest.parsers import parse_gpu_topology


def test_parse_gpu_topology_with_ansi_underlined_header():
    output = (
        '\t\x1b[4mGPU0\tGPU1\tCPU Affinity\tNUMA Affinity\tGPU NUMA ID\x1b[0m\n'
        'GPU0\t X \tPHB\t0-59\t0\t\tN/A\n'
        'GPU1\tPHB\t X \t0-59\t0\t\tN/A\n'
    )
    assert parse_gpu_topology(output) == {'gpus': ['GPU0', 'GPU1'], 'nics': []}
