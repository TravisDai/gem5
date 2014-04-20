# Copyright (c) 2009-2011 Advanced Micro Devices, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Authors: Brad Beckmann

#
# Full system configuraiton for ruby
#

import optparse
import sys

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import addToPath, fatal

addToPath('../common')
addToPath('../ruby')
addToPath('../topologies')

import Ruby

from FSConfig import *
from SysPaths import *
from Benchmarks import *
import Options
import Simulation

parser = optparse.OptionParser()
Options.addCommonOptions(parser)
Options.addFSOptions(parser)

# Add the ruby specific and protocol specific options
Ruby.define_options(parser)

(options, args) = parser.parse_args()
options.ruby = True
clusters=[]
if args:
    print "Error: script doesn't take any positional arguments"
    sys.exit(1)

if options.benchmark:
    try:
        bm = Benchmarks[options.benchmark]
    except KeyError:
        print "Error benchmark %s has not been defined." % options.benchmark
        print "Valid benchmarks are: %s" % DefinedBenchmarks
        sys.exit(1)
else:
    bm = [SysConfig(disk=options.disk_image, mem=options.mem_size)]

# Check for timing mode because ruby does not support atomic accesses
if not (options.cpu_type == "detailed" or options.cpu_type == "timing"):
    print >> sys.stderr, "Ruby requires TimingSimpleCPU or O3CPU!!"
    sys.exit(1)
(CPUClass, test_mem_mode, FutureClass) = Simulation.setCPUClass(options)

TestMemClass = Simulation.setMemClass(options)

for cluster in xrange(2):
    if buildEnv['TARGET_ISA'] == "alpha":
        #system = makeLinuxAlphaRubySystem(test_mem_mode, bm[0])
        clusters.append(makeLinuxAlphaRubySystem(test_mem_mode, bm[0]))
    elif buildEnv['TARGET_ISA'] == "x86":
        #system = makeLinuxX86System(test_mem_mode, options.num_cpus, bm[0], True)
        clusters.append(makeLinuxX86System(test_mem_mode, options.num_cpus, bm[0], True))
        Simulation.setWorkCountOptions(clusters[cluster], options)
    else:
        fatal("incapable of building non-alpha or non-x86 full system!")
# Command line
clusters[0].boot_osflags = 'earlyprintk=ttyS0 console=ttyS0 lpj=7999923 ' + \
                           'root=/dev/hda1'
clusters[0].kernel = binary('x86_64-vmlinux-2.6.22.9')

clusters[0].cache_line_size = options.cacheline_size
clusters[1].cache_line_size = options.cacheline_size


# Create a top-level voltage domain and clock domain
clusters[0].voltage_domain = VoltageDomain(voltage = options.sys_voltage)
clusters[1].voltage_domain = VoltageDomain(voltage = options.sys_voltage)

clusters[0].clk_domain = SrcClockDomain(clock = options.sys_clock,
                                   voltage_domain = clusters[0].voltage_domain)
clusters[1].clk_domain = SrcClockDomain(clock = options.sys_clock,
                                   voltage_domain = clusters[1].voltage_domain)

if options.kernel is not None:
    clusters[0].kernel = binary(options.kernel)

if options.script is not None:
    clusters[0].readfile = options.script

clusters[0].cpu = [CPUClass(cpu_id=i) for i in xrange(options.num_cpus)]
clusters[1].cpu = [CPUClass(cpu_id=i) for i in xrange(options.num_cpus)]
# Create a source clock for the CPUs and set the clock period
clusters[0].cpu_clk_domain = SrcClockDomain(clock = options.cpu_clock,
                                       voltage_domain = clusters[0].voltage_domain)
clusters[1].cpu_clk_domain = SrcClockDomain(clock = options.cpu_clock,
                                       voltage_domain = clusters[1].voltage_domain)

rubysystem0 = Ruby.create_system(options, clusters[0], clusters[0].piobus, clusters[0]._dma_ports)
rubysystem1 = Ruby.create_system(options, clusters[1], clusters[1].piobus, clusters[1]._dma_ports)

# Create a seperate clock domain for Ruby
clusters[0].ruby.clk_domain = SrcClockDomain(clock = options.ruby_clock,
                                        voltage_domain = clusters[0].voltage_domain)
clusters[1].ruby.clk_domain = SrcClockDomain(clock = options.ruby_clock,
                                        voltage_domain = clusters[1].voltage_domain)

for (i, cpu) in enumerate(clusters[0].cpu):
    #
    # Tie the cpu ports to the correct ruby system ports
    #
    cpu.clk_domain = clusters[0].cpu_clk_domain
    cpu.createThreads()
    cpu.createInterruptController()
    cpu.icache_port =  clusters[0].ruby._cpu_ruby_ports[i].slave
    cpu.dcache_port =  clusters[0].ruby._cpu_ruby_ports[i].slave
    if buildEnv['TARGET_ISA'] == "x86":
        cpu.itb.walker.port = clusters[0].ruby._cpu_ruby_ports[i].slave
        cpu.dtb.walker.port = clusters[0].ruby._cpu_ruby_ports[i].slave
        cpu.interrupts.pio = clusters[0].piobus.master
        cpu.interrupts.int_master = clusters[0].piobus.slave
        cpu.interrupts.int_slave = clusters[0].piobus.master

    clusters[0].ruby._cpu_ruby_ports[i].access_phys_mem = True
'''for (i, cpu) in enumerate(clusters[1].cpu):
    #
    # Tie the cpu ports to the correct ruby system ports
    #
    cpu.clk_domain = clusters[1].cpu_clk_domain
    cpu.createThreads()
    cpu.createInterruptController()
    cpu.icache_port =  clusters[1].ruby._cpu_ruby_ports[i].slave
    cpu.dcache_port =  clusters[1].ruby._cpu_ruby_ports[i].slave
    if buildEnv['TARGET_ISA'] == "x86":
        cpu.itb.walker.port = clusters[1].ruby._cpu_ruby_ports[i].slave
        cpu.dtb.walker.port = clusters[1].ruby._cpu_ruby_ports[i].slave
        cpu.interrupts.pio = clusters[1].piobus.master
        cpu.interrupts.int_master = clusters[1].piobus.slave
        cpu.interrupts.int_slave = clusters[1].piobus.master

    clusters[1].ruby._cpu_ruby_ports[i].access_phys_mem = True '''

# Create the appropriate memory controllers and connect them to the
# PIO bus
clusters[0].mem_ctrls = [TestMemClass(range = r) for r in clusters[0].mem_ranges]
clusters[1].mem_ctrls = [TestMemClass(range = r) for r in clusters[1].mem_ranges]
for i in xrange(len(clusters[0].mem_ctrls)):
    clusters[0].mem_ctrls[i].port = clusters[0].piobus.master
for i in xrange(len(clusters[1].mem_ctrls)):
    clusters[1].mem_ctrls[i].port = clusters[1].piobus.master
#clusters[1].membus.master = clusters[1].membus.master[0]


root = Root(full_system = True, system = clusters[0])
Simulation.run(options, root, clusters, FutureClass)


