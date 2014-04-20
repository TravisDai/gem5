# Copyright (c) 2012-2013 ARM Limited
# All rights reserved
# 
# The license below extends only to copyright in the software and shall
# not be construed as granting a license to any other intellectual
# property including but not limited to intellectual property relating
# to a hardware implementation of the functionality of the software
# licensed hereunder.  You may use the software subject to the license
# terms below provided that you ensure that this notice is replicated
# unmodified and in its entirety in all distributions of the software,
# modified or unmodified, in source code or in binary form.
#
# Copyright (c) 2006-2008 The Regents of The University of Michigan
# Copyright (c) 2010 Advanced Micro Devices, Inc.
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
# Authors: Lisa Hsu

import sys
from os import getcwd
from os.path import join as joinpath

import CpuConfig
import MemConfig

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import *

addToPath('../common')

def getCPUClass(cpu_type):
    """Returns the required cpu class and the mode of operation."""
    cls = CpuConfig.get(cpu_type)
    return cls, cls.memory_mode()

def setCPUClass(options):
    """Returns two cpu classes and the initial mode of operation.

       Restoring from a checkpoint or fast forwarding through a benchmark
       can be done using one type of cpu, and then the actual
       simulation can be carried out using another type. This function
       returns these two types of cpus and the initial mode of operation
       depending on the options provided.
    """

    TmpClass, test_mem_mode = getCPUClass(options.cpu_type)
    CPUClass = None
    if TmpClass.require_caches() and \
            not options.caches and not options.ruby:
        fatal("%s must be used with caches" % options.cpu_type)

    if options.checkpoint_restore != None:
        if options.restore_with_cpu != options.cpu_type:
            CPUClass = TmpClass
            TmpClass, test_mem_mode = getCPUClass(options.restore_with_cpu)
    elif options.fast_forward:
        CPUClass = TmpClass
        TmpClass = AtomicSimpleCPU
        test_mem_mode = 'atomic'

    return (TmpClass, test_mem_mode, CPUClass)

def setMemClass(options):
    """Returns a memory controller class."""

    return MemConfig.get(options.mem_type)

def setWorkCountOptions(system, options):
    if options.work_item_id != None:
        system.work_item_id = options.work_item_id
    if options.work_begin_cpu_id_exit != None:
        system.work_begin_cpu_id_exit = options.work_begin_cpu_id_exit
    if options.work_end_exit_count != None:
        system.work_end_exit_count = options.work_end_exit_count
    if options.work_end_checkpoint_count != None:
        system.work_end_ckpt_count = options.work_end_checkpoint_count
    if options.work_begin_exit_count != None:
        system.work_begin_exit_count = options.work_begin_exit_count
    if options.work_begin_checkpoint_count != None:
        system.work_begin_ckpt_count = options.work_begin_checkpoint_count
    if options.work_cpus_checkpoint_count != None:
        system.work_cpus_ckpt_count = options.work_cpus_checkpoint_count

def findCptDir(options, cptdir, testsys):
    """Figures out the directory from which the checkpointed state is read.

    There are two different ways in which the directories holding checkpoints
    can be named --
    1. cpt.<benchmark name>.<instruction count when the checkpoint was taken>
    2. cpt.<some number, usually the tick value when the checkpoint was taken>

    This function parses through the options to figure out which one of the
    above should be used for selecting the checkpoint, and then figures out
    the appropriate directory.
    """

    from os.path import isdir, exists
    from os import listdir
    import re

    if not isdir(cptdir):
        fatal("checkpoint dir %s does not exist!", cptdir)

    cpt_starttick = 0
    if options.at_instruction or options.simpoint:
        inst = options.checkpoint_restore
        if options.simpoint:
            # assume workload 0 has the simpoint
            if testsys.cpu[0].workload[0].simpoint == 0:
                fatal('Unable to find simpoint')
            inst += int(testsys.cpu[0].workload[0].simpoint)

        checkpoint_dir = joinpath(cptdir, "cpt.%s.%s" % (options.bench, inst))
        if not exists(checkpoint_dir):
            fatal("Unable to find checkpoint directory %s", checkpoint_dir)
    else:
        dirs = listdir(cptdir)
        expr = re.compile('cpt\.([0-9]*)')
        cpts = []
        for dir in dirs:
            match = expr.match(dir)
            if match:
                cpts.append(match.group(1))

        cpts.sort(lambda a,b: cmp(long(a), long(b)))

        cpt_num = options.checkpoint_restore
        if cpt_num > len(cpts):
            fatal('Checkpoint %d not found', cpt_num)

        cpt_starttick = int(cpts[cpt_num - 1])
        checkpoint_dir = joinpath(cptdir, "cpt.%s" % cpts[cpt_num - 1])

    return cpt_starttick, checkpoint_dir

def scriptCheckpoints(options, maxtick, cptdir):
    if options.at_instruction or options.simpoint:
        checkpoint_inst = int(options.take_checkpoints)

        # maintain correct offset if we restored from some instruction
        if options.checkpoint_restore != None:
            checkpoint_inst += options.checkpoint_restore

        print "Creating checkpoint at inst:%d" % (checkpoint_inst)
        exit_event = m5.simulate()
        exit_cause = exit_event.getCause()
        print "exit cause = %s" % exit_cause

        # skip checkpoint instructions should they exist
        while exit_cause == "checkpoint":
            exit_event = m5.simulate()
            exit_cause = exit_event.getCause()

        if exit_cause == "a thread reached the max instruction count":
            m5.checkpoint(joinpath(cptdir, "cpt.%s.%d" % \
                    (options.bench, checkpoint_inst)))
            print "Checkpoint written."

    else:
        when, period = options.take_checkpoints.split(",", 1)
        when = int(when)
        period = int(period)
        num_checkpoints = 0

        exit_event = m5.simulate(when - m5.curTick())
        exit_cause = exit_event.getCause()
        while exit_cause == "checkpoint":
            exit_event = m5.simulate(when - m5.curTick())
            exit_cause = exit_event.getCause()

        if exit_cause == "simulate() limit reached":
            m5.checkpoint(joinpath(cptdir, "cpt.%d"))
            num_checkpoints += 1

        sim_ticks = when
        max_checkpoints = options.max_checkpoints

        while num_checkpoints < max_checkpoints and \
                exit_cause == "simulate() limit reached":
            if (sim_ticks + period) > maxtick:
                exit_event = m5.simulate(maxtick - sim_ticks)
                exit_cause = exit_event.getCause()
                break
            else:
                exit_event = m5.simulate(period)
                exit_cause = exit_event.getCause()
                sim_ticks += period
                while exit_event.getCause() == "checkpoint":
                    exit_event = m5.simulate(sim_ticks - m5.curTick())
                if exit_event.getCause() == "simulate() limit reached":
                    m5.checkpoint(joinpath(cptdir, "cpt.%d"))
                    num_checkpoints += 1

    return exit_event

def benchCheckpoints(options, maxtick, cptdir):
    exit_event = m5.simulate(maxtick - m5.curTick())
    exit_cause = exit_event.getCause()

    num_checkpoints = 0
    max_checkpoints = options.max_checkpoints

    while exit_cause == "checkpoint":
        m5.checkpoint(joinpath(cptdir, "cpt.%d"))
        num_checkpoints += 1
        if num_checkpoints == max_checkpoints:
            exit_cause = "maximum %d checkpoints dropped" % max_checkpoints
            break

        exit_event = m5.simulate(maxtick - m5.curTick())
        exit_cause = exit_event.getCause()

    return exit_event

def repeatSwitch(testsys, repeat_switch_cpu_list, maxtick, switch_freq):
    print "starting switch loop"
    while True:
        exit_event = m5.simulate(switch_freq)
        exit_cause = exit_event.getCause()

        if exit_cause != "simulate() limit reached":
            return exit_event

        m5.switchCpus(testsys, repeat_switch_cpu_list)

        tmp_cpu_list = []
        for old_cpu, new_cpu in repeat_switch_cpu_list:
            tmp_cpu_list.append((new_cpu, old_cpu))
        repeat_switch_cpu_list = tmp_cpu_list

        if (maxtick - m5.curTick()) <= switch_freq:
            exit_event = m5.simulate(maxtick - m5.curTick())
            return exit_event

def run(options, root, testsys, cpu_class):
    if options.checkpoint_dir:
        cptdir = options.checkpoint_dir
    elif m5.options.outdir:
        cptdir = m5.options.outdir
    else:
        cptdir = getcwd()

    if options.fast_forward and options.checkpoint_restore != None:
        fatal("Can't specify both --fast-forward and --checkpoint-restore")

    if options.standard_switch and not options.caches:
        fatal("Must specify --caches when using --standard-switch")

    if options.standard_switch and options.repeat_switch:
        fatal("Can't specify both --standard-switch and --repeat-switch")

    if options.repeat_switch and options.take_checkpoints:
        fatal("Can't specify both --repeat-switch and --take-checkpoints")

    np = options.num_cpus
    switch_cpus = None

    if options.prog_interval:
        for i in xrange(np):
            testsys[0].cpu[i].progress_interval = options.prog_interval
            testsys[1].cpu[i].progress_interval = options.prog_interval

    if options.maxinsts:
        for i in xrange(np):
            testsys[0].cpu[i].max_insts_any_thread = options.maxinsts
            testsys[1].cpu[i].max_insts_any_thread = options.maxinsts

    if cpu_class:
        switch_cpus01 = [cpu_class(switched_out=True, cpu_id=(i))
                       for i in xrange(np)]
        ncpuswitch = len(switch_cpus01)
        temp02 = [cpu_class(switched_out=True, cpu_id=(i+ncpuswitch))
                       for i in xrange(np)]
        switch_cpus = switch_cpus01 + temp02

        
        for i in xrange(np):
            if options.fast_forward:
                testsys[0].cpu[i].max_insts_any_thread = int(options.fast_forward)
            switch_cpus[i].system =  testsys[0]
            switch_cpus[i].workload = testsys[0].cpu[i].workload
            switch_cpus[i].clk_domain = testsys[0].cpu[i].clk_domain
            # simulation period
            if options.maxinsts:
                switch_cpus[i].max_insts_any_thread = options.maxinsts
            # Add checker cpu if selected
            if options.checker:
                switch_cpus[i].addCheckerCpu()
        for i in xrange(np):
            if options.fast_forward:
                testsys[1].cpu[i].max_insts_any_thread = int(options.fast_forward)
            switch_cpus[i+ncpuswitch].system =  testsys[1]
            switch_cpus[i+ncpuswitch].workload = testsys[1].cpu[i].workload
            switch_cpus[i+ncpuswitch].clk_domain = testsys[1].cpu[i].clk_domain
            # simulation period
            if options.maxinsts:
                switch_cpus[i+ncpuswitch].max_insts_any_thread = options.maxinsts
            # Add checker cpu if selected
            if options.checker:
                switch_cpus[i+ncpuswitch].addCheckerCpu()

        

        testsys[0].switch_cpus = switch_cpus01
        testsys[1].switch_cpus = temp02
        switch_cpu_list = [(testsys[0].cpu[i], switch_cpus[i]) for i in xrange(np)]
        switch_cpu_list_temp = [(testsys[1].cpu[i], switch_cpus[i+ncpuswitch]) for i in xrange(np)]
        switch_cpu_list = switch_cpu_list + switch_cpu_list_temp

    if options.repeat_switch:
        switch_class = getCPUClass(options.cpu_type)[0]
        if switch_class.require_caches() and \
                not options.caches:
            print "%s: Must be used with caches" % str(switch_class)
            sys.exit(1)
        if not switch_class.support_take_over():
            print "%s: CPU switching not supported" % str(switch_class)
            sys.exit(1)

        repeat_switch_cpus = [switch_class(switched_out=True, \
                                               cpu_id=(i)) for i in xrange(np*2)]

        for i in xrange(np):
            repeat_switch_cpus[i].system = testsys[0]
            repeat_switch_cpus[i].workload = testsys[0].cpu[i].workload
            repeat_switch_cpus[i].clk_domain = testsys[0].cpu[i].clk_domain

            if options.maxinsts:
                repeat_switch_cpus[i].max_insts_any_thread = options.maxinsts

            if options.checker:
                repeat_switch_cpus[i].addCheckerCpu()

        for i in xrange(np):
            repeat_switch_cpus[i+ncpuswitch].system = testsys[1]
            repeat_switch_cpus[i+ncpuswitch].workload = testsys[1].cpu[i].workload
            repeat_switch_cpus[i+ncpuswitch].clk_domain = testsys[1].cpu[i].clk_domain

            if options.maxinsts:
                repeat_switch_cpus[i+ncpuswitch].max_insts_any_thread = options.maxinsts

            if options.checker:
                repeat_switch_cpus[i+ncpuswitch].addCheckerCpu()
        testsys[0].repeat_switch_cpus=[]
        testsys[1].repeat_switch_cpus=[]
        for j in xrange(np*2):
            if j < np:
                testsys[0].repeat_switch_cpus.append(repeat_switch_cpus[j])
            else:
                testsys[1].repeat_switch_cpus.append(repeat_switch_cpus[j])

        if cpu_class:
            repeat_switch_cpu_list = [(switch_cpus[i], repeat_switch_cpus[i])
                                      for i in xrange(np*2)]
        else:
            repeat_switch_cpu_list_1 = [(testsys[0].cpu[i], repeat_switch_cpus[i])
                                      for i in xrange(np)]
            repeat_switch_cpu_list_2 = [(testsys[1].cpu[i+ncpuswitch], repeat_switch_cpus[i+ncpuswitch])
                                      for i in xrange(np)]
            repeat_switch_cpu_list = repeat_switch_cpu_list_1+repeat_switch_cpu_list_2
    if options.standard_switch:
        switch_cpus = [TimingSimpleCPU(switched_out=True, cpu_id=(i))
                       for i in xrange(np*2)]
        switch_cpus_1 = [DerivO3CPU(switched_out=True, cpu_id=(i))
                        for i in xrange(np*2)]

        for i in xrange(np*2):
            if i < np:
                switch_cpus[i].system =  testsys[0]
                switch_cpus_1[i].system =  testsys[0]
                switch_cpus[i].workload = testsys[0].cpu[i].workload
                switch_cpus_1[i].workload = testsys[0].cpu[i].workload
                switch_cpus[i].clk_domain = testsys[0].cpu[i].clk_domain
                switch_cpus_1[i].clk_domain = testsys[0].cpu[i].clk_domain
            else:
                switch_cpus[i].system =  testsys[1]
                switch_cpus_1[i].system =  testsys[1]
                switch_cpus[i].workload = testsys[1].cpu[i].workload
                switch_cpus_1[i].workload = testsys[1].cpu[i].workload
                switch_cpus[i].clk_domain = testsys[1].cpu[i].clk_domain
                switch_cpus_1[i].clk_domain = testsys[1].cpu[i].clk_domain

            # if restoring, make atomic cpu simulate only a few instructions
            if options.checkpoint_restore != None:
                if i < np:
                    testsys[0].cpu[i].max_insts_any_thread = 1
                else:
                    testsys[1].cpu[i].max_insts_any_thread = 1
                    # Fast forward to specified location if we are not restoring
            elif options.fast_forward:
                if i < np:
                    testsys[0].cpu[i].max_insts_any_thread = int(options.fast_forward)
                else:
                    testsys[1].cpu[i].max_insts_any_thread = int(options.fast_forward)
            # Fast forward to a simpoint (warning: time consuming)
            elif options.simpoint:
                if i < np:
                    if testsys[0].cpu[i].workload[0].simpoint == 0:
                        fatal('simpoint not found')
                    testsys[0].cpu[i].max_insts_any_thread = \
                        testsys[0].cpu[i].workload[0].simpoint
                else:
                    if testsys[1].cpu[i].workload[0].simpoint == 0:
                        fatal('simpoint not found')
                    testsys[1].cpu[i].max_insts_any_thread = \
                        testsys[1].cpu[i].workload[0].simpoint
            # No distance specified, just switch
            else:
                if i < np:
                    testsys[0].cpu[i].max_insts_any_thread = 1
                else:
                    testsys[1].cpu[i].max_insts_any_thread = 1

            # warmup period
            if options.warmup_insts:
                switch_cpus[i].max_insts_any_thread =  options.warmup_insts

            # simulation period
            if options.maxinsts:
                switch_cpus_1[i].max_insts_any_thread = options.maxinsts

            # attach the checker cpu if selected
            if options.checker:
                switch_cpus[i].addCheckerCpu()
                switch_cpus_1[i].addCheckerCpu()

        testsys[0].switch_cpus = switch_cpus
        testsys[1].switch_cpus = switch_cpus
        testsys[0].switch_cpus_1 = switch_cpus_1
        testsys[1].switch_cpus_1 = switch_cpus_1
        switch_cpu_list_1 = [(testsys[0].cpu[i], switch_cpus[i]) for i in xrange(np)]
        switch_cpu_list_2 = [(testsys[1].cpu[i], switch_cpus[i]) for i in xrange(np)]
        switch_cpu_list = switch_cpu_list_1+switch_cpu_list_2
        switch_cpu_list1 = [(switch_cpus[i], switch_cpus_1[i]) for i in switch_cpu_list1 ]
        for i in xrange(np*2):
            if i < np: 
                switch_cpu_list1_1=[switch_cpu_list1[i]]
            else: 
                switch_cpu_list1_2=[switch_cpu_list1[i]]
    # set the checkpoint in the cpu before m5.instantiate is called
    if options.take_checkpoints != None and \
           (options.simpoint or options.at_instruction):
        offset = int(options.take_checkpoints)
        # Set an instruction break point
        if options.simpoint:
            for i in xrange(np*2):
                if i < np:
                    if testsys.cpu[i].workload[0].simpoint == 0:
                        fatal('no simpoint for testsys.cpu[%d].workload[0]', i)
                    checkpoint_inst = int(testsys[0].cpu[i].workload[0].simpoint) + offset
                    testsys[0].cpu[i].max_insts_any_thread = checkpoint_inst
                    # used for output below
                    options.take_checkpoints = checkpoint_inst
                else:
                    if testsys[1].cpu[i].workload[0].simpoint == 0:
                        fatal('no simpoint for testsys.cpu[%d].workload[0]', i)
                    checkpoint_inst = int(testsys[1].cpu[i].workload[0].simpoint) + offset
                    testsys[1].cpu[i].max_insts_any_thread = checkpoint_inst
                    # used for output below
                    options.take_checkpoints = checkpoint_inst
        else:
            options.take_checkpoints = offset
            # Set all test cpus with the right number of instructions
            # for the upcoming simulation
            for i in xrange(np*2):
                if i < np:
                    testsys[0].cpu[i].max_insts_any_thread = offset
                else:
                    testsys[1].cpu[i].max_insts_any_thread = offset

    checkpoint_dir = None
    checkpoint_dir1 = None
    if options.checkpoint_restore:
        cpt_starttick, checkpoint_dir = findCptDir(options, cptdir, testsys[0])
        cpt_starttick1, checkpoint_dir1 = findCptDir(options, cptdir, testsys[1])
    m5.instantiate(checkpoint_dir)
    m5.instantiate(checkpoint_dir1)

    # Handle the max tick settings now that tick frequency was resolved
    # during system instantiation
    # NOTE: the maxtick variable here is in absolute ticks, so it must
    # include any simulated ticks before a checkpoint
    explicit_maxticks = 0
    maxtick_from_abs = m5.MaxTick
    maxtick_from_rel = m5.MaxTick
    maxtick_from_maxtime = m5.MaxTick
    explicit_maxticks1 = 0
    maxtick_from_abs1 = m5.MaxTick
    maxtick_from_rel1 = m5.MaxTick
    maxtick_from_maxtime1 = m5.MaxTick
    if options.abs_max_tick:
        maxtick_from_abs = options.abs_max_tick
        explicit_maxticks += 1
        maxtick_from_abs1 = options.abs_max_tick
        explicit_maxticks1 += 1
    if options.rel_max_tick:
        maxtick_from_rel = options.rel_max_tick
        maxtick_from_rel1 = options.rel_max_tick
        if options.checkpoint_restore:
            # NOTE: this may need to be updated if checkpoints ever store
            # the ticks per simulated second
            maxtick_from_rel += cpt_starttick
            maxtick_from_rel1 += cpt_starttick1
            if options.at_instruction or options.simpoint:
                warn("Relative max tick specified with --at-instruction or" \
                     " --simpoint\n      These options don't specify the " \
                     "checkpoint start tick, so assuming\n      you mean " \
                     "absolute max tick")
        explicit_maxticks += 1
        explicit_maxticks1 += 1
    if options.maxtime:
        maxtick_from_maxtime = m5.ticks.fromSeconds(options.maxtime)
        explicit_maxticks += 1
        maxtick_from_maxtime1 = m5.ticks.fromSeconds(options.maxtime)
        explicit_maxticks1 += 1
    if explicit_maxticks > 1:
        warn("Specified multiple of --abs-max-tick, --rel-max-tick, --maxtime."\
             " Using least")
    if explicit_maxticks1 > 1:
        warn("Specified multiple of --abs-max-tick, --rel-max-tick, --maxtime."\
             " Using least")
    maxtick = min([maxtick_from_abs, maxtick_from_rel, maxtick_from_maxtime])
    maxtick1 = min([maxtick_from_abs1, maxtick_from_rel1, maxtick_from_maxtime1])

    if options.checkpoint_restore != None and maxtick < cpt_starttick:
        fatal("Bad maxtick (%d) specified: " \
              "Checkpoint starts starts from tick: %d", maxtick, cpt_starttick)
    if options.checkpoint_restore != None and maxtick1 < cpt_starttick1:
        fatal("Bad maxtick (%d) specified: " \
              "Checkpoint starts starts from tick: %d", maxtick1, cpt_starttick1)

    if options.standard_switch or cpu_class:
        if options.standard_switch:
            print "Switch at instruction count:%s" % \
                    str(testsys[0].cpu[0].max_insts_any_thread)
            print "Switch at instruction count:%s" % \
                    str(testsys[1].cpu[0].max_insts_any_thread)
            exit_event = m5.simulate()
        elif cpu_class and options.fast_forward:
            print "Switch at instruction count:%s" % \
                    str(testsys[0].cpu[0].max_insts_any_thread)
            print "Switch at instruction count:%s" % \
                    str(testsys[1].cpu[0].max_insts_any_thread)       
            exit_event = m5.simulate()
        else:
            print "Switch at curTick count:%s" % str(10000)
            exit_event = m5.simulate(10000)
        print "Switched CPUS @ tick %s" % (m5.curTick())

        m5.switchCpus(testsys[0], switch_cpu_list_1)
        m5.switchCpus(testsys[1], switch_cpu_list_2)

        if options.standard_switch:
            print "Switch at instruction count:%d" % \
                    (testsys[0].switch_cpus[0].max_insts_any_thread)
            print "Switch at instruction count:%d" % \
                    (testsys[1].switch_cpus[0].max_insts_any_thread)
                    

            #warmup instruction count may have already been set
            if options.warmup_insts:
                exit_event = m5.simulate()
            else:
                exit_event = m5.simulate(options.standard_switch)
            print "Switching CPUS @ tick %s" % (m5.curTick())
            print "Simulation ends instruction count:%d" % \
                    (testsys[0].switch_cpus_1[0].max_insts_any_thread)
            print "Simulation ends instruction count:%d" % \
                    (testsys[1].switch_cpus_1[0].max_insts_any_thread)
                    
            m5.switchCpus(testsys[0], switch_cpu_list1_1)
            m5.switchCpus(testsys[1], switch_cpu_list1_2)

    # If we're taking and restoring checkpoints, use checkpoint_dir
    # option only for finding the checkpoints to restore from.  This
    # lets us test checkpointing by restoring from one set of
    # checkpoints, generating a second set, and then comparing them.
    if options.take_checkpoints and options.checkpoint_restore:
        if m5.options.outdir:
            cptdir = m5.options.outdir
            cptdir1 = m5.options.outdir
        else:
            cptdir = getcwd()
            cptdir1 = getcwd()

    if options.take_checkpoints != None :
        # Checkpoints being taken via the command line at <when> and at
        # subsequent periods of <period>.  Checkpoint instructions
        # received from the benchmark running are ignored and skipped in
        # favor of command line checkpoint instructions.
        exit_event = scriptCheckpoints(options, maxtick, cptdir)
        exit_event1 = scriptCheckpoints(options, maxtick1, cptdir1)
    else:
        if options.fast_forward:
            m5.stats.reset()
        print "**** REAL SIMULATION ****"

        # If checkpoints are being taken, then the checkpoint instruction
        # will occur in the benchmark code it self.
        if options.repeat_switch and maxtick > options.repeat_switch:
            exit_event = repeatSwitch(testsys[0], repeat_switch_cpu_list_1,
                                      maxtick, options.repeat_switch)
        else:
            exit_event = benchCheckpoints(options, maxtick, cptdir)
        if options.repeat_switch and maxtick1 > options.repeat_switch:
            exit_event1 = repeatSwitch(testsys[1], repeat_switch_cpu_list_2,
                                      maxtick1, options.repeat_switch)
        else:
            exit_event = benchCheckpoints(options, maxtick, cptdir)
            exit_event1 = benchCheckpoints(options, maxtick1, cptdir1)

    print 'Exiting @ tick %i because %s' % (m5.curTick(), exit_event.getCause())
    if options.checkpoint_at_end:
        m5.checkpoint(joinpath(cptdir, "cpt.%d"))
        m5.checkpoint(joinpath(cptdir1, "cpt.%d"))

    if not m5.options.interactive:
        sys.exit(exit_event.getCode())
        sys.exit(exit_event1.getCode())

