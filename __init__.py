def classFactory(iface):
    from .cluster_generator import ClusterGenerator
    return ClusterGenerator(iface)
