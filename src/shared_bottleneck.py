from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel


def run():
    net = Mininet(
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=True,
    )

    # Hosts
    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")

    # Switches
    s1 = net.addSwitch("s1", failMode="standalone")
    s2 = net.addSwitch("s2", failMode="standalone")

    # Source links
    net.addLink(h1, s1, bw=100, delay="1ms")
    net.addLink(h3, s1, bw=100, delay="1ms")

    # Shared bottleneck: ONLY 10 Mbps
    net.addLink(
    s1,
    s2,
    bw=10,
    delay="5ms",
    max_queue_size=100
)

    # Destination link
    net.addLink(s2, h2, bw=100, delay="1ms")

    net.start()

    print("\n========================================")
    print("     SHARED BOTTLENECK QOS TESTBED")
    print("========================================")
    print("h1 --------\\")
    print("            s1 ===== s2 -------- h2")
    print("h3 --------/       10 Mbps")
    print("")
    print("Source links:      100 Mbps")
    print("Shared bottleneck: 10 Mbps")
    print("Destination:       100 Mbps")
    print("========================================\n")

    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()
