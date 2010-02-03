// __BEGIN_LICENSE__
// Copyright (C) 2006-2009 United States Government as represented by
// the Administrator of the National Aeronautics and Space Administration.
// All Rights Reserved.
// __END_LICENSE__

// ASP
#include <asp/IsisIO/IsisInterface.h>
#include <asp/IsisIO/IsisInterfaceMapFrame.h>
#include <asp/IsisIO/IsisInterfaceFrame.h>
#include <asp/IsisIO/IsisInterfaceMapLineScan.h>
#include <asp/IsisIO/IsisInterfaceLineScan.h>

// ISIS
#include <Filename.h>
#include <Pvl.h>
#include <Camera.h>
#include <CameraFactory.h>

using namespace asp;
using namespace asp::isis;

IsisInterface* IsisInterface::open( std::string const& filename ) {
  // Opening Labels
  Isis::Filename cubefile( filename.c_str() );
  Isis::Pvl label;
  label.Read( cubefile.Expanded() );

  Isis::Camera* camera = Isis::CameraFactory::Create( label );

  switch ( camera->GetCameraType() ) {
  case 0:
    // Framing Camera
    if ( camera->HasProjection )
      return new IsisInterfaceMapFrame( filename );
    else
      return new IsisInterfaceFrame( filename );
  case 2:
    // Linescan Camera
    if ( camera->HasProjection )
      return new IsisInterfaceMapLineScan( filename );
    else
      return new IsisInterfaceLineScan( filename );
  default:
    vw_throw( NoImplErr() << "Don't support Isis Camera Type " << camera->GetCameraType() << " at this moment" );
  }

  return NULL;
}
