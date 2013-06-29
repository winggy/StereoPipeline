#!/usr/bin/env python
# __BEGIN_LICENSE__
#  Copyright (c) 2009-2013, United States Government as represented by the
#  Administrator of the National Aeronautics and Space Administration. All
#  rights reserved.
#
#  The NGT platform is licensed under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance with the
#  License. You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# __END_LICENSE__


import os, glob, optparse, re, shutil, subprocess, sys, string

job_pool = [];

def man(option, opt, value, parser):
    print >>sys.stderr, parser.usage
    print >>sys.stderr, '''\
This program operates on LRO (.IMG) files, and performs the
following ISIS 3 operations:
 * Converts to ISIS format (lronac2isis)
 * Attaches SPICE information (spiceinit and spicefit)
 * Performs radiometric calibration (lronaccal)
 * lronacecho?
 * Removes camera distortions from the CCD images (noproj)
 * Performs jitter analysis (lrojitreg)
 * Mosaics individual CCDs into one unified image file (handmos)
 * Normalizes the mosaic (cubenorm) 
'''

    sys.exit()

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def add_job( cmd, num_working_threads=4 ):
    if ( len(job_pool) >= num_working_threads):
        job_pool[0].wait();
        job_pool.pop(0);
    print cmd;
    job_pool.append( subprocess.Popen(cmd, shell=True) );

def wait_on_all_jobs():
    print "Waiting for jobs to finish";
    while len(job_pool) > 0:
        job_pool[0].wait();
        job_pool.pop(0);

# Go through a list of cubes and sort them into left/right pairs
def build_cube_pairs(cubePaths):
  pairDict = dict();
     
  for cube in cubePaths:
      # Get the image number TODO: in a better manner!
      prefixOffset = len(os.path.dirname(cube)) + 2;
      number = int( cube[prefixOffset:prefixOffset+9] ); 
      sideLetter = cube[prefixOffset+9]
     
      if (number not in pairDict):
          pairDict[number] = ['', ''];
      # Store the path in the spot for either the left or right cube
      if (sideLetter == "L"):
          pairDict[number][0] = cube; # Left
          print "Left --> " + cube;
      else:
          pairDict[number][1] = cube; # Right
          print "Right --> " + cube;
  return pairDict;

def read_flatfile( flat ):
    f = open(flat,'r')
    averages = [0.0,0.0]
    for line in f:
        if ( line.rfind("Average Sample Offset:") >= 0 ):
            print 'FOUND FLAT LINE SAMPLE';
            index       = line.rfind("Offset:");
            index_e     = line.rfind("StdDev:");
            crop        = line[index+7:index_e];
            averages[0] = float(crop);
        elif ( line.rfind("Average Line Offset:") >= 0 ):
            print 'FOUND FLAT LINE LINE';        
            index       = line.rfind("Offset:");
            index_e     = line.rfind("StdDev:");
            crop        = line[index+7:index_e];
            averages[1] = float(crop);
    print str(averages);
    return averages;

#TODO: This should be somewhere else
def isisversion(verbose=False):
    path = ''
    try: path = os.environ['ISISROOT']
    except KeyError, msg:
        raise Exception( "The ISIS environment does not seem to be enabled.\nThe " + str(msg) + " environment variable must be set." )

    version = None
    if os.path.exists( path+'/version' ):
        v = open( path+"/version", 'r')
        version = v.readline().strip()
        v.close()

    f = open(path+"/inc/Constants.h",'r');
    for line in f:
         if ( line.rfind("std::string version(") > 0 ):
            index = line.find("version(\"");
            index_e = line.rfind("|");
            version = line[index+9:index_e].rstrip()
            #version = version +'b'
    f.close() 

    if( version ):
        if( verbose ): print "\tFound Isis Version: "+version+ " at "+path
        alphaend = version.lstrip(string.digits+'.')
        version_numbers = version.rstrip(string.ascii_letters);
        version_strings = version_numbers.split('.')
        version_list = []
        version_list = [int(item) for item in version_strings]
        if( alphaend ): version_list.append( alphaend )
        version_tuple = tuple( version_list )
        return version_tuple

    raise Exception( "Could not find an ISIS version string in " + f.str() )
    return False


# Call lronac2isis on each input file, return list of output files.
def lronac2isis( img_files, threads ):
    lronac2isis_cubs = []
    for img in img_files:
        # Expect to end in .IMG, change to end in .cub
        to_cub = os.path.splitext(img)[0] + '.cub'
        if( os.path.exists(to_cub) ):
            print to_cub + ' exists, skipping lronac2isis.'
        else:
            cmd = 'lronac2isis from= '+ img +' to= '+ to_cub
            add_job(cmd, threads)
        lronac2isis_cubs.append( to_cub )
    wait_on_all_jobs()
    return lronac2isis_cubs


# Call lronaccal on each input file, return list of output files.
def lronaccal( cub_files, threads, delete=False ):
    lronaccal_cubs = []
    for cub in cub_files:
        # Expect to end in .cub, change to end in .lronaccal.cub
        to_cub = os.path.splitext(cub)[0] + '.lronaccal.cub'
        if( os.path.exists(to_cub) ):
            print to_cub + ' exists, skipping lronaccal.'
        else:
            cmd = 'lronaccal from=  '+ cub +' to= '+ to_cub
            add_job(cmd, threads)
        lronaccal_cubs.append( to_cub )
    wait_on_all_jobs()
    
    if( delete ): # Delete all input .cub files and log files
        for cub in cub_files: 
          os.remove( cub )
        lronaccal_log_files = glob.glob( os.path.commonprefix(cub_files) + '*.lronaccal.log' )
        for file in lronaccal_log_files: 
          os.remove( file )
    return lronaccal_cubs
    

# Call lronacecho on each input file, return list of output files.
#TODO: Put in delta option?
def lronacecho( cub_files, threads, delete=False ):
    lronacecho_cubs = []
    for cub in cub_files:
        # Expect to end in .cub, change to end in .lronaccal.cub
        to_cub = os.path.splitext(cub)[0] + '.lronacecho.cub'
        if( os.path.exists(to_cub) ):
            print to_cub + ' exists, skipping lronacecho.'
        else:
            cmd = 'lronacecho from=  '+ cub +' to= '+ to_cub
            add_job(cmd, threads)
        lronacecho_cubs.append( to_cub )
    wait_on_all_jobs()
    
    if( delete ): # Delete all input .cub files and log files
        for cub in cub_files: 
          os.remove( cub )
        #TODO: Are log files generated?
        #lronacecho_log_files = glob.glob( os.path.commonprefix(cub_files) + '*.lronacecho.log' )
        #for file in lronacecho_log_files: 
        #  os.remove( file )
    return lronacecho_cubs


def spice( cub_files, threads):
    for cub in cub_files:
        cmd = 'spiceinit web=false from= '+ cub
        add_job(cmd, threads)
    wait_on_all_jobs()
    for cub in cub_files:
        cmd = 'spicefit from= '+ cub
        add_job(cmd, threads)
    wait_on_all_jobs()
    return

# Left file is in index 0, right is in index 1
def noproj( file_pairs, threads, delete=False ):
    noproj_pairs = dict();
    for k, v in file_pairs.items():
    
        print "v[0] = " + str(v[0]);        
        print "v[1] = " + str(v[1]);                
    
        noproj_pairs[k] = ['', ''];
        for i in range(2): # Process left and right image
          print i;
          to_cub = os.path.splitext(v[i])[0] + '.noproj.cub'
          
          noproj_pairs[k][i] = to_cub; # Add file to output list
          if os.path.exists( to_cub ):
              print to_cub + ' exists, skipping noproj.'
          else:
#              cmd = 'mkdir -p tmp_' + v[i] + '&& '  \
#                        + 'cd tmp_' + v[i] + '&& '  \
#                        + 'noproj from=../'  + v[i] \
#                        +       ' match=../' + v[0] \
#                        + ' source= frommatch to=../'+ to_cub + '&& ' \
#                        + 'cd .. && rm -rf tmp_' + v[i]
              cmd = 'noproj from= '+ v[i]   \
                        + ' to= '  + to_cub \
                        +' match= '+ v[0];
#              print cmd;
              add_job(cmd, threads)
              # print cmd
    wait_on_all_jobs()
    
    if( delete ): # Clean up input cube files
        for v in file_pairs.values(): 
           os.remove( v[0] );
           os.remove( v[1] );           
    return noproj_pairs;


def lronacjitreg( noproj_pairs, threads ):
    
##TODO: Remove cropping code! Note that temps are not deleted!
    
#    # Crop all the files    
#    tempDict = dict();
#    for k,v in noproj_pairs.items(): 
    
#        print "v[0] = " + str(v[0]);        
#        print "v[1] = " + str(v[1]);           
    
#        outFileLeft  = os.path.splitext(v[0])[0] + '.centerline.cub'
#        outFileRight = os.path.splitext(v[1])[0] + '.centerline.cub'        
#        cmdLeft  = 'crop from=' + v[0] + ' to=' + outFileLeft  + ' sample=4900 nsamples=200'
#        cmdRight = 'crop from=' + v[1] + ' to=' + outFileRight + ' sample=4900 nsamples=200'        
#        add_job(cmdLeft,  threads)
#        add_job(cmdRight, threads)        
#        tempDict[k] = (outFileLeft, outFileRight);
        
##        print "outFileLeft  = " + outFileLeft;        
##        print "outFileRight = " + outFileRight;               
        
#    wait_on_all_jobs()
    
   
    boundsCommands = '--correlator-type 2 --xkernel 15 --ykernel 15 --pyramid --h-corr-min 0 --h-corr-max 60 --v-corr-min -50 --v-corr-max -10 --cropWidth 200';
    for k,v in noproj_pairs.items(): 
#        cmd = 'lronacjitreg ' + boundsCommands   \
        cmd = '~/repot/StereoPipelineFork/StereoPipeline/src/asp/Tools/lronacjitreg ' + boundsCommands   \
            + ' --rowLog /root/data/auto/logs/rowLog_'+str(k)+'.txt' \
            + ' '+ v[0] \
            + ' '+ v[1];
        add_job(cmd, threads)
    wait_on_all_jobs()

    # Read in all the shift values from the output text files
    averages = dict()
    for k,v in noproj_pairs.items():
        flat_file = '/root/data/auto/logs/rowLog_'+str(k)+'.txt'
        print 'Reading log file ' + flat_file;
        averages[k] = read_flatfile( flat_file )
#        os.remove( flat_file )

    return averages


def mosaic( noproj_pairs, averages, threads ):

    mosaicList = dict();
    for k,v in noproj_pairs.items(): 
    
        # Create mosaic output file
        mosaicPath = os.path.splitext(v[0])[0] + '.mosaic.cub'
        shutil.copy( v[0], mosaicPath ) # Copy the LE image to the output path
    
        xOffset = averages[k][0]
        yOffset = averages[k][1]        
    
        handmos( v[1], mosaicPath,
                 str( int(round( xOffset )) ),
                 str( int(round( yOffset )) ),
                 threads )
        mosaicList[k] = mosaicPath;
                 
    wait_on_all_jobs()

    return mosaicList


def handmos( fromcub, tocub, outsamp, outline, threads ):

    offsetSample = 4900 + int(outsamp);
    cmd = 'handmos from= '+ fromcub +' mosaic= '+ tocub \
            +' outsample= '+ str(offsetSample) \
            +' insample= 4900'   \
            +' outline= '  + outline \
            +' matchbandbin=FALSE priority=ontop';
#TODO: Get crop number to use with insample!      
#TODO: Do anything with the top?      

#    if( isisversion() > (3,1,20) ):
#        # ISIS 3.1.21+
#        cmd += ' priority= beneath'
#    else:
#        # ISIS 3.1.20-
#        cmd += ' input= beneath'
    add_job(cmd, threads);
    return


def cubenorm( mosaicList, threads, delete=False ):

    normedList = dict();
    for k,v in mosaicList.items(): 
    
        normedPath = os.path.splitext(v)[0] + '.norm.cub'
   
        cmd = 'cubenorm from= '+ v +' to= '+ normedPath
        add_job(cmd, threads);
       
        normedList[k] = normedPath;
                 
    wait_on_all_jobs()

    if( delete ): # Clean up input cube files
        for v in mosaicList.values(): 
           os.remove(v);

    return normedList

#--------------------------------------------------------------------------------

def main():

    try:
        try:
            #TODO: File name format?
            usage = "usage: lronac2mosaic.py [--help][--manual][--threads N]" \
                    "[--keep][-m match] HiRISE-EDR.IMG-files\n  [ASP 2.2.2_post]"
            parser = optparse.OptionParser(usage=usage)
#            parser.set_defaults(delete =True)
            parser.set_defaults(delete =False)
#            parser.set_defaults(match  =5)
#            parser.set_defaults(threads=4)
            parser.set_defaults(threads=1)
            parser.add_option("--manual", action="callback", callback=man,
                              help="Read the manual.")
            parser.add_option("--stop-at-no-proj", dest="stop_no_proj", action="store_true",
                              help="Process the IMG files only to have SPICE attached.")
#            parser.add_option("--resume-at-no-proj", dest="resume_no_proj", action="store_true",
#                              help="Pick back up after spiceinit has happened. " /
#                                   "This was noproj uses your new camera information") 
            parser.add_option("-t", "--threads", dest="threads",
                              help="Number of threads to use.",type="int")
#            parser.add_option("-m", "--match", dest="match",
#                              help="CCD number of match CCD")
            parser.add_option("-k", "--keep", action="store_false",
                              dest="delete",
                              help="Will not delete intermediate files.")

            (options, args) = parser.parse_args()

            if not args: parser.error("need .IMG files")

        except optparse.OptionError, msg:
            raise Usage(msg)

        # # Determine Isis Version
        # post_isis_20 = is_post_isis_3_1_20();
        isisversion( True )

        print "Beginning processing....."

        if 1:#not options.resume_no_proj: # If not skipping to later point
            print "lronac2isis"
            # lronac2isis - Per-file operation, returns list of new files
            lronac2isised = lronac2isis( args, options.threads )

            print "spice"
            # Attach spice info to cubes (adds to existing files)
            spice( lronac2isised, options.threads )

# --> This is missing data files!
            print "lronaccal"
#            # lronaccal - Per-file operation, returns list of new files
            lronaccaled = lronaccal( lronac2isised, options.threads, options.delete )

            print "lronacecho"
            # lronacecho - Per-file operation, returns list of new files
            lronacechod = lronacecho( lronac2isised, options.threads, options.delete )

        if options.stop_no_proj: # Stop early if requested
            print "Finished"
            return 0

#        if options.resume_no_proj: # If resume option was set
#            lronacechod = args

        print "build_cube_pairs"
        # TODO: Update this step, it just needs to get the files into left/right pairs.
        lronac_file_pairs = build_cube_pairs( lronacechod )

        print "noproj"
        # noproj - Per-file operation
        noprojed_file_pairs = noproj( lronac_file_pairs, options.threads, options.delete )

        print "lronacjitreg"
        # lronacjitreg - Determines mean shift for each file pair
        averages = lronacjitreg( noprojed_file_pairs, options.threads )

        print "mosaic"
        # mosaic handmos - Use mean shifts to combine the file pairs
        mosaicked = mosaic( noprojed_file_pairs, averages, options.threads )

        # Clean up noproj files
        if( options.delete ):
          for cub in noprojed_file_pairs.values():
              os.remove( cub )

        # Run a final cubenorm across the image:
        cubenorm( mosaicked, options.threads, options.delete )

        print "Finished"
        return 0

    except Usage, err:
        print >>sys.stderr, err.msg
        # print >>sys.stderr, "for help use --help"
        return 2

	# To more easily debug this program, comment out this catch block.
    # except Exception, err:
    #     sys.stderr.write( str(err) + '\n' )
    #     return 1


if __name__ == "__main__":
    sys.exit(main())